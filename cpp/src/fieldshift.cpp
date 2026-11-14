#include "fieldshift/fieldshift.h"

#include <cmath>

namespace {

// mean Earth radius in kilometres
constexpr double kEarthRadiusKm = 6371.0088;

// (double degrees)
// degrees to radians
double to_rad(double deg) { return deg * M_PI / 180.0; }

} // namespace

extern "C" {

const char* fs_version(void) { return "0.1.0"; }

double fs_haversine_km(double lat1, double lon1, double lat2, double lon2) {
    const double dlat = to_rad(lat2 - lat1);
    const double dlon = to_rad(lon2 - lon1);
    const double a = std::sin(dlat / 2) * std::sin(dlat / 2) +
                     std::cos(to_rad(lat1)) * std::cos(to_rad(lat2)) *
                     std::sin(dlon / 2) * std::sin(dlon / 2);
    return 2.0 * kEarthRadiusKm * std::asin(std::sqrt(a));
}

double fs_ndvi(double nir, double red) {
    const double sum = nir + red;
    return sum == 0.0 ? 0.0 : (nir - red) / sum;
}

int fs_ndvi_array(const double* nir, const double* red, double* out, size_t n) {
    if (n > 0 && (!nir || !red || !out)) return -1;
    for (size_t i = 0; i < n; ++i) out[i] = fs_ndvi(nir[i], red[i]);
    return 0;
}

} // extern "C"
