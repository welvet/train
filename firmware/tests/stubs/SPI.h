#ifndef FIRMWARE_TEST_SPI_H
#define FIRMWARE_TEST_SPI_H

class SPIClass {
 public:
  void begin() { began = true; }

  bool began = false;
};

inline SPIClass SPI;

#endif
