// Experimental CPU-only diffuse photon propagation benchmark, no real devices.
#include "lighting_bench_common.hpp"
#include <array>

static void quad(std::vector<Vec>& verts,std::vector<Triangle>& tris,Vec a,Vec b,Vec c,Vec d){
 uint32_t n=verts.size();verts.insert(verts.end(),{a,b,c,d});
 tris.push_back({n,n+1,n+2});tris.push_back({n,n+2,n+3});
}
static void make_room(std::vector<Vec>& v,std::vector<Triangle>& t,float width,float height){
 const float z=3.0f;
 quad(v,t,{-1,-1,0},{width,-1,0},{width,height,0},{-1,height,0});
 quad(v,t,{-1,-1,z},{-1,height,z},{width,height,z},{width,-1,z});
 quad(v,t,{-1,-1,0},{-1,-1,z},{width,-1,z},{width,-1,0});
 quad(v,t,{-1,height,0},{width,height,0},{width,height,z},{-1,height,z});
 quad(v,t,{-1,-1,0},{-1,height,0},{-1,height,z},{-1,-1,z});
 quad(v,t,{width,-1,0},{width,-1,z},{width,height,z},{width,height,0});
}
struct Sample {uint64_t rays=0, contacts=0; double light_weight=0;};
static void diffuse(Vec& direction,Vec normal,uint32_t& seed){
 // A cosine-weighted hemisphere for a Lambertian surface, not a full BRDF renderer.
 normal=unit(normal);
 Vec tangent=unit(cross((std::fabs(normal.z)>.9f)?Vec{0,1,0}:Vec{0,0,1},normal));
 Vec side=cross(normal,tangent);
 const float phi=6.283185307179586f*rand01(seed), r=std::sqrt(rand01(seed)),h=std::sqrt(1-r*r);
 direction=unit({tangent.x*r*std::cos(phi)+side.x*r*std::sin(phi)+normal.x*h,
                 tangent.y*r*std::cos(phi)+side.y*r*std::sin(phi)+normal.y*h,
                 tangent.z*r*std::cos(phi)+side.z*r*std::sin(phi)+normal.z*h});
}
static Sample simulate(RTCScene scene,int photons,int depth,float xsize,float ysize){
 Sample s;RTCIntersectArguments args;rtcInitIntersectArguments(&args);uint32_t seed=0x145293ac;
 for(int j=0;j<photons;j++){
  Vec orig={xsize/2.f,ysize/2.f,2.7f};
  Vec target={rand01(seed)*xsize,rand01(seed)*ysize,rand01(seed)*2.0f};
  Vec dir=unit(sub(target,orig));float weight=1.0f;
  for(int bounce=0;bounce<depth;bounce++){
   RTCRayHit h={};h.ray.org_x=orig.x;h.ray.org_y=orig.y;h.ray.org_z=orig.z;
   h.ray.dir_x=dir.x;h.ray.dir_y=dir.y;h.ray.dir_z=dir.z;
   h.ray.tnear=.002f;h.ray.tfar=1000.f;h.ray.mask=~0u;
   h.hit.geomID=RTC_INVALID_GEOMETRY_ID;
   rtcIntersect1(scene,&h,&args);s.rays++;
   if(h.hit.geomID==RTC_INVALID_GEOMETRY_ID)break;
   s.contacts++;s.light_weight+=weight;
   Vec n={h.hit.Ng_x,h.hit.Ng_y,h.hit.Ng_z};
   if(dot(n,dir)>0)n={-n.x,-n.y,-n.z};
   orig={orig.x+dir.x*h.ray.tfar,orig.y+dir.y*h.ray.tfar,orig.z+dir.z*h.ray.tfar};
   weight*=.75f;
   diffuse(dir,n,seed);
   orig={orig.x+dir.x*.003f,orig.y+dir.y*.003f,orig.z+dir.z*.003f};
  }
 }
 return s;
}
int main(){
 RTCDevice d=rtcNewDevice("threads=2");if(!d){puts("no_embree_device");return 2;}
 puts("workload=CPU-only synthetic diffuse 3D photon paths; no MIS/direct lighting/pixels; CPU-only local host");
 for(int boxes:{2,256}){
  std::vector<Vec> v;std::vector<Triangle> t;
  int nx=boxes==2?2:16,ny=boxes/nx;
  for(int idx=0;idx<boxes;idx++)add_box(v,t,1.1f*(idx%nx),1.1f*(idx/nx));
  float w=1.1f*nx+1.f,hh=1.1f*ny+1.f;
  make_room(v,t,w,hh);
  RTCScene scene=rtcNewScene(d);RTCGeometry g=rtcNewGeometry(d,RTC_GEOMETRY_TYPE_TRIANGLE);
  Vec* vv=(Vec*)rtcSetNewGeometryBuffer(g,RTC_BUFFER_TYPE_VERTEX,0,RTC_FORMAT_FLOAT3,sizeof(Vec),v.size());
  std::copy(v.begin(),v.end(),vv);
  Triangle* tt=(Triangle*)rtcSetNewGeometryBuffer(g,RTC_BUFFER_TYPE_INDEX,0,RTC_FORMAT_UINT3,sizeof(Triangle),t.size());
  std::copy(t.begin(),t.end(),tt);
  rtcCommitGeometry(g);rtcAttachGeometry(scene,g);rtcReleaseGeometry(g);rtcCommitScene(scene);
  for(int max_bounces:{1,2,4,8}){
   const int count=50000;
   auto start=std::chrono::steady_clock::now();
   Sample s=simulate(scene,count,max_bounces,w,hh);
   double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
   std::printf("boxes=%d bounces=%d photons=%d ray_queries=%llu contacts=%llu elapsed_ms=%.3f rays_per_sec=%.0f photons_per_sec=%.0f weighted_radiance_sum=%.3f\n",
          boxes,max_bounces,count,(unsigned long long)s.rays,(unsigned long long)s.contacts,seconds*1000,s.rays/seconds,count/seconds,s.light_weight);
  }
  rtcReleaseScene(scene);
 }
 rtcReleaseDevice(d);
 struct rusage usage={};getrusage(RUSAGE_SELF,&usage);std::printf("peak_rss_kib=%ld\n",usage.ru_maxrss);
}
