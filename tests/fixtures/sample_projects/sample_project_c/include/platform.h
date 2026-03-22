#ifndef PLATFORM_H
#define PLATFORM_H

#if defined(_WIN32) || defined(_WIN64)
  #define PCG_PLATFORM_WINDOWS 1
#else
  #define PCG_PLATFORM_POSIX 1
#endif

#endif
