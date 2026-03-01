#include <Arduino.h>

// your lcd pins

#define LCD_RS  26
#define LCD_E   25

uint8_t LCD_D[8] = {16,17,18,19,21,22,23,27};

uint32_t lcdDataMask = 0;

// bitbanging type shit

inline void lcdRS(bool state) {
  if (state)
    GPIO.out_w1ts = (1UL << LCD_RS);
  else
    GPIO.out_w1tc = (1UL << LCD_RS);
}

inline void lcdPulseEnable() {
  GPIO.out_w1ts = (1UL << LCD_E);
  delayMicroseconds(75);
  GPIO.out_w1tc = (1UL << LCD_E);
  delayMicroseconds(75);
}

inline void lcdWrite8(uint8_t value) {
  GPIO.out_w1tc = lcdDataMask;

  uint32_t outMask = 0;
  for (int i = 0; i < 8; i++) {
    if (value & (1 << i))
      outMask |= (1UL << LCD_D[i]);
  }

  GPIO.out_w1ts = outMask;
  lcdPulseEnable();
}

inline void lcdCommand(uint8_t cmd) {
  lcdRS(0);
  lcdWrite8(cmd);
}

inline void lcdData(uint8_t data) {
  lcdRS(1);
  lcdWrite8(data);
}

void lcdSetCursor(uint8_t col, uint8_t row) {
  lcdCommand(0x80 | (row ? (0x40 + col) : col));
}



void lcdInit() {

  pinMode(LCD_RS, OUTPUT);
  pinMode(LCD_E, OUTPUT);

  for (int i = 0; i < 8; i++) {
    pinMode(LCD_D[i], OUTPUT);
    lcdDataMask |= (1UL << LCD_D[i]);
  }

  delay(50);

  lcdCommand(0x38);
  lcdCommand(0x0C);
  lcdCommand(0x01);
  delay(5);
  lcdCommand(0x06);
}

// load ze memory

void lcdLoadSet(uint8_t set[8][8]) {
  lcdCommand(0x40);

  for (int c = 0; c < 8; c++)
    for (int r = 0; r < 8; r++)
      lcdData(set[c][r]);

  lcdCommand(0x80);
}

// dual buffer

typedef struct {
  uint8_t A[8][8];
  uint8_t B[8][8];
  uint8_t C[8][8];
  uint8_t D[8][8];
} CharsetBank;

CharsetBank bankFront;
CharsetBank bankBack;

volatile bool frameReady = false;
portMUX_TYPE swapMux = portMUX_INITIALIZER_UNLOCKED;

// core 0

#define FB_WIDTH  80
#define FB_HEIGHT 16

uint8_t framebuffer[FB_HEIGHT][FB_WIDTH];



inline void clearFramebuffer() {
  memset(framebuffer, 0, sizeof(framebuffer));
}

inline void drawPixel(int x, int y) {
  if (x < 0 || x >= FB_WIDTH) return;
  if (y < 0 || y >= FB_HEIGHT) return;
  framebuffer[y][x] = 1;
}

// line draw
void drawLine(int x0, int y0, int x1, int y1) {
  int dx = abs(x1 - x0);
  int sx = x0 < x1 ? 1 : -1;
  int dy = -abs(y1 - y0);
  int sy = y0 < y1 ? 1 : -1;
  int err = dx + dy;

  while (true) {
    drawPixel(x0, y0);
    if (x0 == x1 && y0 == y1) break;
    int e2 = 2 * err;
    if (e2 >= dy) { err += dy; x0 += sx; }
    if (e2 <= dx) { err += dx; y0 += sy; }
  }
}

// tile extraction

void extractTileToBank(int tileX, int tileY, uint8_t dest[8]) {

  int startX = tileX * 5;
  int startY = tileY * 8;

  for (int row = 0; row < 8; row++) {

    uint8_t packed = 0;

    for (int col = 0; col < 5; col++) {
      if (framebuffer[startY + row][startX + col]) {
        packed |= (1 << (4 - col));  
      }
    }

    dest[row] = packed;
  }
}

// render loop

void renderTask(void *pvParameters) {


  while (1) {

    clearFramebuffer();

    // PUT YOUR COMMANDS HERE
    drawLine(0,0, 79,15);
    drawLine(79,0, 0,15);
    drawLine(0,0, 0,15);
    drawLine(0,15, 79,15);
    drawLine(0,0, 79,0);
    drawLine(79,0, 79,15);

    for (int tileY = 0; tileY < 2; tileY++) {
      for (int tileX = 0; tileX < 16; tileX++) {

        uint8_t tempTile[8];
        extractTileToBank(tileX, tileY, tempTile);

        if (tileY == 0) {
          if (tileX % 2 == 0)
            memcpy(bankBack.A[tileX/2], tempTile, 8);
          else
            memcpy(bankBack.B[tileX/2], tempTile, 8);
        }
        else {
          if (tileX % 2 == 0)
            memcpy(bankBack.C[tileX/2], tempTile, 8);
          else
            memcpy(bankBack.D[tileX/2], tempTile, 8);
        }
      }
    }


    portENTER_CRITICAL(&swapMux);
    frameReady = true;
    portEXIT_CRITICAL(&swapMux);

    vTaskDelay(pdMS_TO_TICKS(30));
  }
}

// core 1

void lcdTask(void *pvParameters) {

  while (1) {

    // Check if new frame ready
    bool doSwap = false;

    portENTER_CRITICAL(&swapMux);
    if (frameReady) {
      doSwap = true;
      frameReady = false;
    }
    portEXIT_CRITICAL(&swapMux);

    if (doSwap) {
      portENTER_CRITICAL(&swapMux);
      CharsetBank temp = bankFront;
      bankFront = bankBack;
      bankBack = temp;
      portEXIT_CRITICAL(&swapMux);
    }

    
    for (int x = 0; x < 4; x++) {

      switch (x){
        case 0:
          lcdLoadSet(bankFront.A);
          lcdSetCursor(0, 0); 
          break;

        case 1:
          lcdLoadSet(bankFront.D);
          lcdSetCursor(1, 1); 
          break;

        case 2:
          lcdLoadSet(bankFront.B);
          lcdSetCursor(1, 0);
          break;

        case 3:
          lcdLoadSet(bankFront.C);
          lcdSetCursor(0, 1);
          break;
      }

      for (int i = 0; i < 8; i++) {
        lcdData(i);
        lcdData(' ');
      }

      for (int i = 0; i < 80; i++){
        lcdData(' ');
      }
    }

    // Small yield so FreeRTOS stays happy
    vTaskDelay(1);
  }
}

/* ================= SETUP ================= */

void setup() {

  lcdInit();

  xTaskCreatePinnedToCore(
    renderTask,
    "Renderer",
    4096,
    NULL,
    1,
    NULL,
    0   // Core 0
  );

  xTaskCreatePinnedToCore(
    lcdTask,
    "LCD",
    4096,
    NULL,
    1,
    NULL,
    1   // Core 1
  );
}

/* ================= LOOP UNUSED ================= */

void loop() {}