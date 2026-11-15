// Independent virtual range oracle. Only the experiment driver sees true pose.
// Reuses tested scene from behavior_lab; no device, network or motor control.
#define main embree_behavior_sensor_unused_main
#include "../behavior_lab/embree_sensor.cpp"
#undef main
#include <sstream>
#include <string>
int main() {
    try {
        Sensor sensor;
        std::cout.setf(std::ios::fixed);
        std::cout.precision(5);
        std::string row;
        while (std::getline(std::cin, row)) {
            std::istringstream in(row);
            float x, y, heading, a, b, c;
            std::string trailing;
            if (!(in >> x >> y >> heading >> a >> b >> c) || (in >> trailing)
                || !std::isfinite(x) || !std::isfinite(y) || !std::isfinite(heading)
                || !std::isfinite(a) || !std::isfinite(b) || !std::isfinite(c)
                || x < 0 || x > 10 || y < 0 || y > 8
                || std::fabs(heading) > 100 || std::fabs(a) > 3.14f
                || std::fabs(b) > 3.14f || std::fabs(c) > 3.14f) {
                std::cout << "error\n" << std::flush; continue;
            }
            std::cout << sensor.trace(x, y, heading + a) << ' '
                      << sensor.trace(x, y, heading + b) << ' '
                      << sensor.trace(x, y, heading + c) << '\n' << std::flush;
        }
    } catch (const std::exception& e) {
        std::cerr << "embree_angles_error=" << e.what() << '\n';return 2;
    }
}
