// Embree-backed source for the DPH1 synthetic 2D event laboratory.
// Ray intersection is performed in actual 3D by Embree, at z=1 metre.
// Only the first validated, cardinal hit becomes a 2D event. No motor/net I/O.
// Geometry and semantic object labels live exclusively on this source/evaluator.
#include "lighting_bench_common.hpp"
#include <array>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <stdexcept>
#include <sys/stat.h>
#include <unistd.h>

struct Vec2mm { int32_t x,y; };
struct Launch { Vec2mm at,velocity; };
constexpr std::array<Launch, 8> RAYS = {{
 {{0,3000},{1000,0}},{{10000,3000},{-1000,0}},
 {{3000,0},{0,1000}},{{3000,8000},{0,-1000}},
 {{0,5000},{1000,0}},{{10000,5000},{-1000,0}},
 {{7000,0},{0,1000}},{{7000,8000},{0,-1000}},
}};

static void append_u32(std::vector<uint8_t>& bytes,uint32_t n){
 for(int b=0;b<4;b++)bytes.push_back(uint8_t(n>>(8*b)));
}
static void append_i32(std::vector<uint8_t>& bytes,int32_t n){append_u32(bytes,uint32_t(n));}
static void append_u64(std::vector<uint8_t>& bytes,uint64_t n){
 for(int b=0;b<8;b++)bytes.push_back(uint8_t(n>>(8*b)));
}
static void head(std::vector<uint8_t>& bytes,uint8_t kind,uint32_t sequence,uint32_t tick){
 bytes.insert(bytes.end(),{'D','P','H','1',1,kind,0,0});
 append_u32(bytes,0x44524f53); // same synthetic scene ID as Rust, not a home identifier
 append_u32(bytes,sequence);append_u32(bytes,tick);
}
static void epoch(std::vector<uint8_t>& bytes){
 head(bytes,0,0,0);append_i32(bytes,10000);append_i32(bytes,8000);
 append_u64(bytes,1900000000000ULL);append_u32(bytes,50);
}
static void emission(std::vector<uint8_t>& bytes,uint32_t id,uint32_t tick,Launch launch){
 head(bytes,1,id*2-1,tick);append_u32(bytes,id);
 append_i32(bytes,launch.at.x);append_i32(bytes,launch.at.y);
 append_i32(bytes,launch.velocity.x);append_i32(bytes,launch.velocity.y);
}
static void contact(std::vector<uint8_t>& bytes,uint32_t id,uint32_t tick,uint32_t object,
                    Vec2mm at,Vec2mm normal){
 head(bytes,2,id*2,tick);append_u32(bytes,id);append_u32(bytes,object);
 append_i32(bytes,at.x);append_i32(bytes,at.y);
 append_i32(bytes,normal.x);append_i32(bytes,normal.y);
}

struct Scene {
 RTCDevice device = nullptr;
 RTCScene scene = nullptr;
 std::array<uint32_t,2> geomIDs{};
 Scene(){
  device=rtcNewDevice("threads=2");if(!device)throw std::runtime_error("embree_device_unavailable");
  scene=rtcNewScene(device);if(!scene)throw std::runtime_error("embree_scene_unavailable");
  for(uint32_t index=0;index<2;index++){
   std::vector<Vec> verts;std::vector<Triangle> tris;
   // Same x-y boundaries as the Rust canonical 10m by 8m synthetic scene.
   const float x = index==0 ? 2.f : 6.f, y=index==0 ? 2.f : 4.f;
   // Reuse box-mesh generation but expand the reference box to 2m x 2m.
   const float lo=0.f,hi=2.f;
   std::array<Vec,8> v = {{{x,y,lo},{x+2,y,lo},{x+2,y+2,lo},{x,y+2,lo},
                            {x,y,hi},{x+2,y,hi},{x+2,y+2,hi},{x,y+2,hi}}};
   verts.assign(v.begin(),v.end());
   constexpr int faces[6][4]={{0,3,2,1},{4,5,6,7},{0,1,5,4},
                              {1,2,6,5},{2,3,7,6},{3,0,4,7}};
   for(auto& f:faces){tris.push_back({uint32_t(f[0]),uint32_t(f[1]),uint32_t(f[2])});
                       tris.push_back({uint32_t(f[0]),uint32_t(f[2]),uint32_t(f[3])});}
   RTCGeometry g=rtcNewGeometry(device,RTC_GEOMETRY_TYPE_TRIANGLE);
   auto* vertices=static_cast<Vec*>(rtcSetNewGeometryBuffer(
        g,RTC_BUFFER_TYPE_VERTEX,0,RTC_FORMAT_FLOAT3,sizeof(Vec),verts.size()));
   auto* triangles=static_cast<Triangle*>(rtcSetNewGeometryBuffer(
        g,RTC_BUFFER_TYPE_INDEX,0,RTC_FORMAT_UINT3,sizeof(Triangle),tris.size()));
   if(!vertices || !triangles)throw std::runtime_error("embree_geometry_buffer_failed");
   std::copy(verts.begin(),verts.end(),vertices);
   std::copy(tris.begin(),tris.end(),triangles);
   rtcCommitGeometry(g);geomIDs[index]=rtcAttachGeometry(scene,g);rtcReleaseGeometry(g);
  }
  rtcCommitScene(scene);
  if(rtcGetDeviceError(device)!=RTC_ERROR_NONE)throw std::runtime_error("embree_commit_failed");
 }
 ~Scene(){if(scene)rtcReleaseScene(scene);if(device)rtcReleaseDevice(device);}
 Scene(const Scene&)=delete;Scene& operator=(const Scene&)=delete;
};

struct Hit {uint32_t object;Vec2mm at,normal;uint32_t flight;};
static Hit fire(RTCScene scene,std::array<uint32_t,2> ids,Launch launch){
 RTCRayHit h={};
 h.ray.org_x=float(launch.at.x)/1000.f;h.ray.org_y=float(launch.at.y)/1000.f;
 h.ray.org_z=1.f;h.ray.dir_x=float(launch.velocity.x)/1000.f;
 h.ray.dir_y=float(launch.velocity.y)/1000.f;h.ray.dir_z=0;
 h.ray.tnear=.0001f;h.ray.tfar=1000.f;h.ray.mask=~0u;
 h.hit.geomID=RTC_INVALID_GEOMETRY_ID;
 RTCIntersectArguments args;rtcInitIntersectArguments(&args);
 rtcIntersect1(scene,&h,&args);
 if(h.hit.geomID==RTC_INVALID_GEOMETRY_ID)throw std::runtime_error("synthetic_ray_missed");
 int n=-1;
 for(int i=0;i<2;i++)if(ids[i]==h.hit.geomID)n=i;
 if(n<0)throw std::runtime_error("unexpected_geometry_id");
 auto flight=uint32_t(std::lround(h.ray.tfar));
 if(flight==0 || std::fabs(float(flight)-h.ray.tfar)>.0001f)
  throw std::runtime_error("hit_off_logical_tick_grid");
 Vec2mm at={launch.at.x+launch.velocity.x*int(flight),
            launch.at.y+launch.velocity.y*int(flight)};
 Vec2mm normal={0,0};
 if(launch.velocity.x>0)normal.x=-1;
 if(launch.velocity.x<0)normal.x=1;
 if(launch.velocity.y>0)normal.y=-1;
 if(launch.velocity.y<0)normal.y=1;
 // The face normal must oppose travel; use Embree normal only for sanity.
 const Vec geometric={h.hit.Ng_x,h.hit.Ng_y,h.hit.Ng_z};
 if(std::fabs(dot(geometric,{float(normal.x),float(normal.y),0.f}))<.9f)
  throw std::runtime_error("face_normal_mismatch");
 return {uint32_t(n+1),at,normal,flight};
}

static bool write_private(const std::string& path,const std::vector<uint8_t>& blob){
 // O_EXCL and O_NOFOLLOW block accidental file overwrite and symlinks.
 int fd=open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,0600);
 if(fd<0)return false;
 size_t pos=0;bool success=true;
 while(pos<blob.size()){
  auto n=write(fd,blob.data()+pos,blob.size()-pos);
  if(n<0 && errno==EINTR)continue;
  if(n<=0){success=false;break;}
  pos+=size_t(n);
 }
 if(close(fd)!=0)success=false;
 if(!success)unlink(path.c_str());
 return success;
}

int main(int argc,char** argv){
 if(argc!=3 || std::strcmp(argv[1],"--output")!=0){
  std::fprintf(stderr,"usage: embree_photon_events --output NEW_PRIVATE_FILE\n");return 2;
 }
 try{
  Scene scene;
  std::vector<uint8_t> events;events.reserve(712);
  epoch(events);
  auto started=std::chrono::steady_clock::now();
  uint64_t traced=0;
  for(uint32_t i=0;i<RAYS.size();i++){
   auto launch=RAYS[i];auto tick=1+i*12;
   emission(events,i+1,tick,launch);
   auto hit=fire(scene.scene,scene.geomIDs,launch);traced++;
   contact(events,i+1,tick+hit.flight,hit.object,hit.at,hit.normal);
  }
  const double initial_ms=std::chrono::duration<double,std::milli>(
      std::chrono::steady_clock::now()-started).count();
  // Repeated Embree intersections without serializing one packet per hit.
  started=std::chrono::steady_clock::now();
  for(int i=0;i<100000;i++){
   (void)fire(scene.scene,scene.geomIDs,RAYS[size_t(i)%RAYS.size()]);
   traced++;
  }
  const double traversal_ms=std::chrono::duration<double,std::milli>(
      std::chrono::steady_clock::now()-started).count();
  if(events.size()!=712)throw std::runtime_error("incorrect_fixed_journal_size");
  if(!write_private(argv[2],events))throw std::runtime_error("cannot_write_new_private_file");
  std::fprintf(stderr,"embree_generated_event_bytes=%zu frames=17 sampled_rays=8 ",events.size());
  std::fprintf(stderr,"initial_sample_ms=%.3f benchmark_rays=100000 benchmark_ms=%.3f ",
               initial_ms,traversal_ms);
  std::fprintf(stderr,"benchmark_rays_s=%.0f total_embree_intersections=%llu\n",
               100000.0*1000.0/traversal_ms,(unsigned long long)traced);
  return 0;
 }catch(const std::exception& error){
  std::fprintf(stderr,"embree_photon_events_error=%s\n",error.what());return 3;
 }
}
