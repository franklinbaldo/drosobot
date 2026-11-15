#include "lighting_bench_common.hpp"

int main(){
 RTCDevice device=rtcNewDevice("threads=2");
 if(!device){std::fprintf(stderr,"Embree device creation failed\n");return 2;}
 std::printf("benchmark=Embree4.3.3-versus-MollerTrumbore, scope=primary_ray_box_intersections, hardware=local_host\n");
 for(int nboxes: {2,256,1024}){
  std::vector<Vec> vertices;std::vector<Triangle> triangles;
  int nx=(nboxes==2?2:int(std::sqrt(nboxes))),ny=nboxes/nx;
  for(int idx=0;idx<nboxes;idx++)add_box(vertices,triangles,float(idx%nx)*1.1f,float(idx/nx)*1.1f);
  auto build_start=std::chrono::steady_clock::now();
  RTCScene scene=rtcNewScene(device);
  RTCGeometry geom=rtcNewGeometry(device,RTC_GEOMETRY_TYPE_TRIANGLE);
  Vec* p=(Vec*)rtcSetNewGeometryBuffer(geom,RTC_BUFFER_TYPE_VERTEX,0,RTC_FORMAT_FLOAT3,sizeof(Vec),vertices.size());
  std::copy(vertices.begin(),vertices.end(),p);
  Triangle* t=(Triangle*)rtcSetNewGeometryBuffer(geom,RTC_BUFFER_TYPE_INDEX,0,RTC_FORMAT_UINT3,sizeof(Triangle),triangles.size());
  std::copy(triangles.begin(),triangles.end(),t);
  rtcCommitGeometry(geom);rtcAttachGeometry(scene,geom);rtcReleaseGeometry(geom);rtcCommitScene(scene);
  auto built=std::chrono::steady_clock::now();
  auto rays=make_rays(80000,nx,ny);
  RTCIntersectArguments args;rtcInitIntersectArguments(&args);
  for(int i=0;i<2000;i++)intersects(scene,rays[i],args); // warmup
  int64_t hits=0;
  auto start=std::chrono::steady_clock::now();
  for(const auto& ray:rays)hits+=intersects(scene,ray,args);
  auto stop=std::chrono::steady_clock::now();
  auto ms=std::chrono::duration<double,std::milli>(stop-start).count();
  auto build_ms=std::chrono::duration<double,std::milli>(built-build_start).count();
  int ncheck=nboxes==2?80000:1500;
  int64_t naivehits=0;
  auto brute_start=std::chrono::steady_clock::now();
  for(int i=0;i<ncheck;i++)naivehits+=naive(rays[i],vertices,triangles);
  auto brute_stop=std::chrono::steady_clock::now();
  auto brute_ms=std::chrono::duration<double,std::milli>(brute_stop-brute_start).count();
  int correct=0;
  for(int i=0;i<std::min(2000,ncheck);i++)correct+=naive(rays[i],vertices,triangles)==intersects(scene,rays[i],args);
  const int tested=std::min(2000,ncheck);
  std::printf("boxes=%d triangles=%zu rays=%zu hits=%lld build_ms=%.3f embree_ms=%.3f embree_rays_s=%.0f naive_rays=%d naive_hits=%lld naive_ms=%.3f naive_rays_s=%.0f parity=%d/%d\n",
    nboxes,triangles.size(),rays.size(),(long long)hits,build_ms,ms,rays.size()*1000./ms,ncheck,
    (long long)naivehits,brute_ms,ncheck*1000./brute_ms,correct,tested);
  rtcReleaseScene(scene);
 }
 struct rusage usage={};getrusage(RUSAGE_SELF,&usage);
 std::printf("peak_rss_kib=%ld\n",usage.ru_maxrss);
 rtcReleaseDevice(device);
}
