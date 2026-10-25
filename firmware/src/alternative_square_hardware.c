/********************************** (C) COPYRIGHT  *******************************
* 逻辑分析仪：GPIO 采样在 TIM2 中断里进行（环形缓冲），主循环只负责 USB 发送
* 这样 USB 发送阻塞期间采样不中断、不丢点，时间轴准确
* 【方波版】开机直接在 PA15 输出 1kHz 方波，A15->D0
* 用法：用本文件替换 Common/hardware.c 后重新编译，即得到 Square_1kHz 固件
*******************************************************************************/
#include "hardware.h"
#include "ch32h417_usbfs_device.h"

#define BATCH_POINTS 1000
static uint8_t batch_buf[BATCH_POINTS];

/* ===== 采样环形缓冲（中断写 / 主循环读） ===== */
#define RING_SIZE 2048   /* 必须是 2 的幂，容纳 USB 阻塞期间的采样 */
static uint8_t  cap_ring[RING_SIZE];
static volatile uint16_t ring_head = 0;
static volatile uint16_t ring_tail = 0;

/* ===== 软件 UART 信号源（方波模式下不使用，保留以便切回 UART） ===== */
static const char sig_msg[] = "Hello CH32!\r\n";
#define SIG_LEN         (sizeof(sig_msg) - 1)
#define TICKS_PER_BIT   10    /* 100us * 10 = 1ms/bit -> 1000bps @10kHz */
#define BITS_PER_FRAME  10    /* 起始位 + 8数据位 + 停止位 */

static volatile uint8_t sig_active = 0;
static uint8_t sig_char;
static uint8_t sig_bit;
static uint8_t sig_tick;
static uint16_t sig_restart_cnt;   /* 空闲时计数，到点重发 */

/* ===== 信号发生器模式：0=软件UART, 1=方波 ===== */
volatile uint8_t sig_mode = 0;
volatile uint16_t sig_square_div = 5;  /* 方波半周期tick数：freq=10000/(2*div)，div=5->1kHz */
static uint16_t sig_square_cnt = 0;

/* ===== PC 命令接收（USB 端点2） ===== */
__attribute__((aligned(4))) uint8_t cmd_dma_buf[64];   /* 端点2 DMA 落点 */
static char cmd_line[32];
static uint8_t cmd_len = 0;
volatile uint8_t last_cmd = 0;   /* 最后有效命令：1=方波, 0=UART */

static void USB_SendBuf(const uint8_t *data, uint16_t len)
{
    uint16_t off = 0;
    while(off < len)
    {
        uint16_t chunk = len - off;
        if(chunk > DEF_USBD_ENDP3_SIZE) chunk = DEF_USBD_ENDP3_SIZE;
        while((USBFSD->UEP3_TX_CTRL & USBFS_UEP_T_RES_MASK) != USBFS_UEP_T_RES_NAK);
        memcpy(USBFS_EP3_Buf, data + off, chunk);
        USBFSD->UEP3_TX_LEN = chunk;
        USBFSD->UEP3_TX_CTRL = (USBFSD->UEP3_TX_CTRL & ~USBFS_UEP_T_RES_MASK)
                             | USBFS_UEP_T_RES_ACK;
        off += chunk;
    }
}

/* 采样脚 PD0-7：上拉输入 */
static void Capture_GPIO_Init(void)
{
    GPIO_InitTypeDef g = {0};
    RCC_HB2PeriphClockCmd(RCC_HB2Periph_GPIOD, ENABLE);
    g.GPIO_Pin = GPIO_Pin_0 | GPIO_Pin_1 | GPIO_Pin_2 | GPIO_Pin_3
               | GPIO_Pin_4 | GPIO_Pin_5 | GPIO_Pin_6 | GPIO_Pin_7;
    g.GPIO_Mode = GPIO_Mode_IPU;
    GPIO_Init(GPIOD, &g);
}

/* 软件 UART 引脚：PA15 普通推挽输出；PC6 诊断输出 */
static void Signal_Init(void)
{
    GPIO_InitTypeDef g = {0};

    RCC_HB2PeriphClockCmd(RCC_HB2Periph_GPIOA, ENABLE);
    g.GPIO_Pin   = GPIO_Pin_15;
    g.GPIO_Speed = GPIO_Speed_Very_High;
    g.GPIO_Mode  = GPIO_Mode_Out_PP;
    GPIO_Init(GPIOA, &g);

    GPIOA->BSHR = GPIO_Pin_15;   /* 空闲高 */
    sig_active = 0;

    /* 诊断：PC6 推挽输出，每个 OUT 包翻转一次 */
    RCC_HB2PeriphClockCmd(RCC_HB2Periph_GPIOC, ENABLE);
    g.GPIO_Pin   = GPIO_Pin_6;
    g.GPIO_Speed = GPIO_Speed_Very_High;
    g.GPIO_Mode  = GPIO_Mode_Out_PP;
    GPIO_Init(GPIOC, &g);
    GPIOC->BCR = GPIO_Pin_6;
}

static void set_line(uint8_t v)
{
    if(v) GPIOA->BSHR = GPIO_Pin_15;
    else  GPIOA->BCR  = GPIO_Pin_15;
}

void Signal_Start(void)
{
    sig_char   = 0;
    sig_bit    = 0;
    sig_tick   = 0;
    sig_active = 1;
    set_line(0);   /* 起始位 */
}

void Signal_Tick(void)
{
    /* 方波模式：分频翻转 PA15，freq = 10000/(2*div) */
    if(sig_mode == 1)
    {
        if(sig_square_div == 0) sig_square_div = 1;
        sig_square_cnt++;
        if(sig_square_cnt >= sig_square_div)
        {
            sig_square_cnt = 0;
            GPIOA->OUTDR ^= GPIO_Pin_15;
        }
        return;
    }

    if(!sig_active)
    {
        /* 空闲：计数到 2000 tick = 200ms，重发一次（在中断边界对齐） */
        sig_restart_cnt++;
        if(sig_restart_cnt >= 2000)
        {
            sig_restart_cnt = 0;
            Signal_Start();
        }
        return;
    }
    sig_restart_cnt = 0;

    sig_tick++;
    if(sig_tick < TICKS_PER_BIT) return;
    sig_tick = 0;

    sig_bit++;
    if(sig_bit >= BITS_PER_FRAME)
    {
        sig_char++;
        if(sig_char >= SIG_LEN)
        {
            sig_active = 0;
            set_line(1);
            return;
        }
        sig_bit = 0;
        set_line(0);
    }
    else if(sig_bit <= 8)
    {
        set_line(((uint8_t)sig_msg[sig_char] >> (sig_bit - 1)) & 0x01);
    }
    else
    {
        set_line(1);
    }
}

/* 由 TIM2 中断每 100us 调用：采样入环形缓冲 */
void Capture_Tick(void)
{
    uint16_t next = (ring_head + 1) & (RING_SIZE - 1);
    if(next != ring_tail)   /* 缓冲未满 */
    {
        cap_ring[ring_head] = (uint8_t)(GPIOD->INDR & 0x00FF);
        ring_head = next;
    }
}

/* 端点2 收到一包数据（USB 中断里调用）：逐字符即时处理 */
int Signal_HandleRx(const uint8_t *data, uint16_t len)
{
    uint16_t i;
    int ret = -1;
    for(i = 0; i < len; i++)
    {
        char c = (char)data[i];
        if(c == 'u' || c == 'U')
        {
            /* u 立即切 UART，不等换行 */
            sig_mode = 0;
            Signal_Start();
            last_cmd = 0;
            ret = 0;
        }
        else if(c == 'S' || c == 's')
        {
            /* S 立即切方波（默认1kHz），开始累积数字，换行时再定频率 */
            cmd_len = 0;
            cmd_line[cmd_len++] = 'S';
            sig_mode = 1;
            sig_square_div = 5;
            last_cmd = 1;
            ret = 1;
        }
        else if(c >= '0' && c <= '9')
        {
            if(cmd_len > 0 && cmd_line[0] == 'S' && cmd_len < sizeof(cmd_line) - 1)
                cmd_line[cmd_len++] = c;
        }
        else if(c == '\r' || c == '\n')
        {
            /* S 命令换行：解析设 div、切方波 */
            if(cmd_len > 0 && cmd_line[0] == 'S')
            {
                cmd_line[cmd_len] = 0;
                Cmd_Parse(cmd_line);   /* 只设置 div */
                sig_mode = 1;
                last_cmd = 1;
                ret = 1;
                cmd_len = 0;
            }
        }
    }
    return ret;
}

/* 解析一条命令：返回 1=切方波，0=切UART，-1=无效 */
int Cmd_Parse(const char *line)
{
    if(line[0] == 'S' || line[0] == 's')
    {
        /* S<频率Hz>：只设置 div，如 S1000 -> div=5 */
        uint32_t f = 0;
        const char *p = line + 1;
        while(*p >= '0' && *p <= '9') { f = f * 10 + (uint32_t)(*p - '0'); p++; }
        if(f < 1) f = 1000;
        if(f > 5000) f = 5000;          /* 10kHz 下最高 5kHz */
        sig_square_div = (uint16_t)(10000 / (2 * f));
        if(sig_square_div < 1) sig_square_div = 1;
        last_cmd = 1;
        return 1;
    }
    if(line[0] == 'U' || line[0] == 'u')
    {
        sig_mode = 0;
        Signal_Start();
        last_cmd = 0;
        return 0;
    }
    return -1;
}

void Hardware(void)
{
    uint16_t batch_cnt = 0;

    printf("Build Time: %s %s\n", __DATE__, __TIME__);

    RCC_Configuration();
    TIM2_Init();
    Capture_GPIO_Init();
    Signal_Init();

    /* ===== 固定方波模式：开机直接输出 1kHz 方波（不经过 USB 命令，无干扰） ===== */
    sig_mode = 1;
    sig_square_div = 5;   /* 10000/(2*5)=1000Hz */

    printf("Signal Fixed Square Wave on PA15, 1000Hz\n");

    USBFS_RCC_Init();
    USBFS_Device_Init(ENABLE);
    /* 固定方波由 Signal_Tick 直接产生，无需 Signal_Start */

    while(1)
    {
        /* 从环形缓冲取数据，攒满一批发送；USB 阻塞不影响中断采样 */
        while(ring_tail != ring_head)
        {
            batch_buf[batch_cnt++] = cap_ring[ring_tail];
            ring_tail = (ring_tail + 1) & (RING_SIZE - 1);

            if(batch_cnt >= BATCH_POINTS)
            {
                USB_SendBuf(batch_buf, BATCH_POINTS);
                batch_cnt = 0;
            }
        }
    }
}
