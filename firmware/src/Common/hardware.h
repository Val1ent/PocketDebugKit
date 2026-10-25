/********************************** (C) COPYRIGHT  *******************************
* File Name          : hardware.h
* Author             : WCH
* Version            : V1.0.0
* Date               : 2025/03/01
* Description        : This file contains all the functions prototypes for the 
*                      hardware.
*********************************************************************************
* Copyright (c) 2025 Nanjing Qinheng Microelectronics Co., Ltd.
* Attention: This software (modified or not) and binary are used for 
* microcontroller manufactured by Nanjing Qinheng Microelectronics.
*******************************************************************************/
#ifndef __HARDWARE_H
#define __HARDWARE_H

#ifdef __cplusplus
 extern "C" {
#endif

#include "ch32h417.h"
#include "debug.h"

	 
void Hardware(void);
void Capture_Tick(void);
void Signal_Start(void);
void Signal_Tick(void);
int  Signal_HandleRx(const uint8_t *data, uint16_t len);
int  Cmd_Parse(const char *line);

extern uint8_t cmd_dma_buf[64];
extern volatile uint8_t sig_mode;
extern volatile uint16_t sig_square_div;
extern volatile uint8_t last_cmd;

#ifdef __cplusplus
}
#endif

#endif 





