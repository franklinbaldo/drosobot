// Read-only synthetic geometric sensor for a 10-minute virtual robot test.
// Only stdin commands and stdout readings. No UDP, HTTP, motors or credentials.
// Scene: 10x8 metre room; solid boxes [2,4]x[2,4], [6,8]x[4,6].
// Input: x y heading_rad (pose known only to simulator/evaluator).
// Output: front_m left_45_m right_45_m light_level_arb, or error.
#include <embree4/rtcore.h>
#include <algorithm>
#include <cmath>
#include <iostream>
#include <iomanip>
#include <vector>
#include <array>
#include <limits>
#include <stdexcept>

struct Vec { float x,y,z; };
struct Tri { unsigned a,b,c; };
static void make_box(std::vector<Vec>& v,std::vector<Tri>& t,float a,float b,float c,float d,float bottom,float top) {
  const unsigned o=static_cast<unsigned>(v.size());
  for(auto p:std::array<Vec,8>{{{a,b,bottom},{c,b,bottom},{c,d,bottom},{a,d,bottom},
       {a,b,top},{c,b,top},{c,d,top},{a,d,top}}}) v.push_back(p);
  constexpr unsigned faces[6][4]={{0,3,2,1},{4,5,6,7},{0,1,5,4},
      {1,2,6,5},{2,3,7,6},{3,0,4,7}};
  for(auto& f:faces){t.push_back({o+f[0],o+f[1],o+f[2]});t.push_back({o+f[0],o+f[2],o+f[3]});}
}
struct Sensor {
  RTCDevice device=nullptr;RTCScene scene=nullptr;
  Sensor() {
    device=rtcNewDevice("threads=2");if(!device)throw std::runtime_error("device_creation_failed");
    scene=rtcNewScene(device);if(!scene)throw std::runtime_error("scene_creation_failed");
    std::vector<Vec> v;std::vector<Tri> t;
    make_box(v,t,0,0,10,8,-.08,0); // floor
    make_box(v,t,0,0,10,8,2.8,2.88); // ceiling
    make_box(v,t,-.08,0,0,8,0,2.8);make_box(v,t,10,0,10.08,8,0,2.8);
    make_box(v,t,0,-.08,10,0,0,2.8);make_box(v,t,0,8,10,8.08,0,2.8);
    make_box(v,t,2,2,4,4,0,2);make_box(v,t,6,4,8,6,0,2);
    RTCGeometry g=rtcNewGeometry(device,RTC_GEOMETRY_TYPE_TRIANGLE);
    auto* vv=static_cast<Vec*>(rtcSetNewGeometryBuffer(g,RTC_BUFFER_TYPE_VERTEX,0,RTC_FORMAT_FLOAT3,sizeof(Vec),v.size()));
    auto* tt=static_cast<Tri*>(rtcSetNewGeometryBuffer(g,RTC_BUFFER_TYPE_INDEX,0,RTC_FORMAT_UINT3,sizeof(Tri),t.size()));
    if(!vv||!tt)throw std::runtime_error("buffer_allocation_failed");
    std::copy(v.begin(),v.end(),vv);std::copy(t.begin(),t.end(),tt);
    rtcCommitGeometry(g);rtcAttachGeometry(scene,g);rtcReleaseGeometry(g);rtcCommitScene(scene);
  }
  ~Sensor(){if(scene)rtcReleaseScene(scene);if(device)rtcReleaseDevice(device);}
  float trace(float x,float y,float theta,float z=.4f,float max_range=4.f) const {
    RTCRayHit h={};h.ray.org_x=x;h.ray.org_y=y;h.ray.org_z=z;
    h.ray.dir_x=std::cos(theta);h.ray.dir_y=std::sin(theta);h.ray.dir_z=0;
    h.ray.tnear=.001f;h.ray.tfar=max_range;h.ray.mask=~0u;
    h.hit.geomID=RTC_INVALID_GEOMETRY_ID;
    RTCIntersectArguments args;rtcInitIntersectArguments(&args);rtcIntersect1(scene,&h,&args);
    return h.hit.geomID==RTC_INVALID_GEOMETRY_ID?max_range:h.ray.tfar;
  }
  float light(float x,float y) const {
    // This is an intentionally simplified lighting surrogate: inverse-square
    // visibility to ceiling lights (NO full global illumination here).
    static const std::array<Vec,2> lamps={{{1,1,2.6f},{8.5f,7.f,2.6f}}};
    float light=0;
    for(const Vec& l:lamps){
      Vec delta={l.x-x,l.y-y,l.z-.4f};
      const float dist=std::sqrt(delta.x*delta.x+delta.y*delta.y+delta.z*delta.z);
      RTCRayHit h={};h.ray.org_x=x;h.ray.org_y=y;h.ray.org_z=.4f;
      h.ray.dir_x=delta.x/dist;h.ray.dir_y=delta.y/dist;h.ray.dir_z=delta.z/dist;
      h.ray.tnear=.005f;h.ray.tfar=dist-.02f;h.ray.mask=~0u;
      h.hit.geomID=RTC_INVALID_GEOMETRY_ID;
      RTCIntersectArguments args;rtcInitIntersectArguments(&args);rtcIntersect1(scene,&h,&args);
      if(h.hit.geomID==RTC_INVALID_GEOMETRY_ID) light+=20.f/(1.f+dist*dist);
    }
    return light;
  }
};
int main() {
  try {
    Sensor sensor;
    std::cout<<std::fixed<<std::setprecision(5);
    float x,y,heading;
    while(std::cin>>x>>y>>heading) {
      if(!std::isfinite(x)||!std::isfinite(y)||!std::isfinite(heading)||
         x<0||x>10||y<0||y>8||std::fabs(heading)>100) {
        std::cout<<"error\n"<<std::flush;continue;
      }
      constexpr float diagonal=.78539816339f;
      std::cout<<sensor.trace(x,y,heading)<<" "
               <<sensor.trace(x,y,heading-diagonal)<<" "
               <<sensor.trace(x,y,heading+diagonal)<<" "
               <<sensor.light(x,y)<<"\n"<<std::flush;
    }
  }catch(const std::exception& e){std::cerr<<"embree_sensor_failure="<<e.what()<<"\n";return 2;}
}
