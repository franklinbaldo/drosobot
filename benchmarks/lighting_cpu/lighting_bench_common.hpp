#pragma once
// Shared synthetic CPU-lighting benchmark primitives, not full global illumination.
#include <embree4/rtcore.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <sys/resource.h>

struct Vec {float x,y,z;};
struct Triangle {uint32_t v0,v1,v2;};
struct Ray {Vec org,dir;};
Vec sub(Vec a,Vec b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
Vec cross(Vec a,Vec b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
float dot(Vec a,Vec b){return a.x*b.x+a.y*b.y+a.z*b.z;}
Vec unit(Vec a){float q=std::sqrt(dot(a,a));return {a.x/q,a.y/q,a.z/q};}
void add_box(std::vector<Vec>& vertices,std::vector<Triangle>& indices,float x,float y){
 float minx=x,miny=y,maxx=x+.85f,maxy=y+.85f,lo=0,hi=1.6f;
 uint32_t k=vertices.size();
 Vec v[8]={{minx,miny,lo},{maxx,miny,lo},{maxx,maxy,lo},{minx,maxy,lo},
           {minx,miny,hi},{maxx,miny,hi},{maxx,maxy,hi},{minx,maxy,hi}};
 vertices.insert(vertices.end(),v,v+8);
 const int faces[6][4]={{0,3,2,1},{4,5,6,7},{0,1,5,4},{1,2,6,5},{2,3,7,6},{3,0,4,7}};
 for(const auto& f: faces){indices.push_back({k+(uint32_t)f[0],k+(uint32_t)f[1],k+(uint32_t)f[2]});
                          indices.push_back({k+(uint32_t)f[0],k+(uint32_t)f[2],k+(uint32_t)f[3]});}
}
uint32_t step(uint32_t& state){state=state*1664525u+1013904223u;return state;}
float rand01(uint32_t& state){return float(step(state)>>8)*0x1p-24f;}
std::vector<Ray> make_rays(int n,int nx,int ny){
 std::vector<Ray> rays; rays.reserve(n); uint32_t seed=0x12345678u;
 Vec org={float(nx)*.55f,-4.0f,2.1f};
 for(int i=0;i<n;i++){
  Vec dst={rand01(seed)*float(nx)*1.1f,rand01(seed)*float(ny)*1.1f,rand01(seed)*2.0f};
  rays.push_back({org,unit(sub(dst,org))});
 }
 return rays;
}
// Basic brute-force ray-triangle intersection (Moller-Trumbore): correctness comparator.
bool naive(const Ray& r,const std::vector<Vec>& v,const std::vector<Triangle>& tr){
 for(const Triangle& t:tr){
  Vec a=v[t.v0],e1=sub(v[t.v1],a),e2=sub(v[t.v2],a);
  Vec p=cross(r.dir,e2); float det=dot(e1,p);
  if(std::fabs(det)<1.e-8f)continue;
  float inv=1.0f/det;Vec q=sub(r.org,a);
  float u=dot(q,p)*inv;
  if(u<0 || u>1)continue;
  Vec w=cross(q,e1);float vv=dot(r.dir,w)*inv;
  if(vv<0 || u+vv>1)continue;
  float distance=dot(e2,w)*inv;
  if(distance>0.001f && distance<1000.0f)return true;
 }
 return false;
}
bool intersects(RTCScene scene,const Ray& r,RTCIntersectArguments& args){
 RTCRayHit hit={};
 hit.ray.org_x=r.org.x;hit.ray.org_y=r.org.y;hit.ray.org_z=r.org.z;
 hit.ray.dir_x=r.dir.x;hit.ray.dir_y=r.dir.y;hit.ray.dir_z=r.dir.z;
 hit.ray.tnear=.001f;hit.ray.tfar=1000.0f;hit.ray.mask=~0u;
 hit.hit.geomID=RTC_INVALID_GEOMETRY_ID;
 rtcIntersect1(scene,&hit,&args);
 return hit.hit.geomID!=RTC_INVALID_GEOMETRY_ID;
}
