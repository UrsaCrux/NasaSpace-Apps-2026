// fieldshift.h - C++ core exposed to Python.
//
// Every function here is extern "C" so Python can load it with ctypes,
// see fieldshift/native/__init__.py. Document each declaration with a
// minidoc comment directly above it; its optional first line lists the
// arguments between parentheses.
//
// NOTE: do not write parentheses in comments or macros right above the
// extern "C" line below: minidoc would take the block for a function body
// and skip every declaration in it.
#ifndef FIELDSHIFT_FIELDSHIFT_H
#define FIELDSHIFT_FIELDSHIFT_H

#include <stddef.h>

#include "fieldshift/export.h"

#ifdef __cplusplus
extern "C" {
#endif

// ()
// version of the library as "major.minor.patch"; the string is static, do not free it
FS_API const char* fs_version(void);

// (double lat1, double lon1, double lat2, double lon2)
// great-circle distance in kilometres between two points given in degrees
FS_API double fs_haversine_km(double lat1, double lon1, double lat2, double lon2);

// (double nir, double red)
// normalised difference vegetation index (nir - red) / (nir + red), in [-1, 1];
// returns 0 when nir + red is 0
FS_API double fs_ndvi(double nir, double red);

// (const double* nir, const double* red, double* out, size_t n)
// NDVI of n pixel pairs written to out; returns 0 on success, -1 on a null pointer
FS_API int fs_ndvi_array(const double* nir, const double* red, double* out, size_t n);

#ifdef __cplusplus
}
#endif

#endif // FIELDSHIFT_FIELDSHIFT_H
