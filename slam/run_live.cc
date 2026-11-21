// Persistent RGB-only runner. Requests and replies are correlated by sequence/time.
#include <stella_vslam/config.h>
#include <stella_vslam/system.h>
#include <stella_vslam/publish/map_publisher.h>
#include <stella_vslam/publish/frame_publisher.h>
#include <stella_vslam/data/landmark.h>
#include <stella_vslam/data/keyframe.h>
#include <opencv2/imgcodecs.hpp>
#include <spdlog/spdlog.h>
#include <spdlog/sinks/stdout_color_sinks.h>
#include <filesystem>
#include <iostream>
#include <sstream>
#include <iomanip>
#include <chrono>
#include <set>
#include <algorithm>

int main(int argc,char** argv){
 if(argc!=5)return 1;
 try{
  spdlog::set_default_logger(spdlog::stderr_color_mt("live"));
  const auto root=std::filesystem::canonical(argv[3]);
  const std::filesystem::path output(argv[4]);
  auto cfg=std::make_shared<stella_vslam::config>(argv[1]);
  auto slam=std::make_shared<stella_vslam::system>(cfg,argv[2]);
  slam->startup();
  std::cout<<"@@SLAM {\"ready\":true}\n"<<std::flush;
  try{
   std::string line;double previous=-1;unsigned int epoch=0;bool had_map=false;
   while(std::getline(std::cin,line)){
    if(line=="QUIT")break;
    unsigned long long seq;double timestamp;std::string filename;int want_keyframes=0;
    std::istringstream input(line);
    cv::Mat image;
    const auto input_start=std::chrono::steady_clock::now();
    if(line.rfind("FRAME ",0)==0){
     std::string tag;unsigned long bytes;
     if(!(input>>tag>>seq>>timestamp>>bytes)||bytes!=640*480*3)throw std::runtime_error("Invalid live image header");
     input>>want_keyframes;
     image=cv::Mat(480,640,CV_8UC3);
     std::cin.read(reinterpret_cast<char*>(image.data),bytes);
     if(static_cast<unsigned long>(std::cin.gcount())!=bytes)throw std::runtime_error("Truncated live image");
    }else{
     if(!(input>>seq>>timestamp>>filename))throw std::runtime_error("Invalid live request");
     input>>want_keyframes;
     auto path=std::filesystem::canonical(root/filename);
     auto rel=path.lexically_relative(root);
     if(rel.empty()||rel.is_absolute()||*rel.begin()=="..")throw std::runtime_error("Frame path escapes root");
     image=cv::imread(path.string(),cv::IMREAD_COLOR);
    }
    if(!std::isfinite(timestamp)||timestamp<=previous)throw std::runtime_error("Invalid live timestamp");
    const double input_ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-input_start).count();
    if(image.cols!=640||image.rows!=480)throw std::runtime_error("Live SLAM requires 640x480");
    previous=timestamp;
    auto started=std::chrono::steady_clock::now();
    auto pose=slam->feed_monocular_frame(image,timestamp); // Camera-to-world.
    double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-started).count();
    std::ostringstream out;out<<std::setprecision(15)<<"@@SLAM {\"sequence\":"<<seq<<",\"timestamp\":"<<timestamp<<",\"tracking_ms\":"<<ms<<",\"pose\":";
    if(pose&&pose->allFinite()){
     out<<'[';for(int r=0;r<4;++r)for(int c=0;c<4;++c){if(r||c)out<<',';out<<(*pose)(r,c);}out<<']';
    }else out<<"null";
    auto write_points=[&out](const auto& points){
     out<<'[';bool first=true;unsigned int count=0;
     for(const auto& point:points){
      if(!point||point->will_be_erased()||point->num_observations()<2)continue;
      const auto p=point->get_pos_in_world();if(!p.allFinite())continue;
      if(!first)out<<',';first=false;out<<'['<<p.x()<<','<<p.y()<<','<<p.z()<<']';
      if(++count>=10000)break;
     }out<<']';
    };
    out<<",\"observed\":";write_points(slam->get_frame_publisher()->get_landmarks());
    std::vector<std::shared_ptr<stella_vslam::data::landmark>> all;
    std::set<std::shared_ptr<stella_vslam::data::landmark>> local;
    slam->get_map_publisher()->get_landmarks(all,local);
    if(all.empty()&&had_map){++epoch;had_map=false;}
    if(!all.empty())had_map=true;
    out<<",\"map_epoch\":"<<epoch<<",\"input_ms\":"<<input_ms<<",\"sparse\":";write_points(all);
    if(want_keyframes){
     // IDs and positions are captured together; keyframes refer into this snapshot.
     out<<",\"landmarks\":[";bool first=true;unsigned int count=0;
     std::set<unsigned int> available;
     for(const auto& point:all){
      if(!point||point->will_be_erased()||point->num_observations()<2)continue;
      auto p=point->get_pos_in_world();if(!p.allFinite())continue;
      if(!first)out<<',';first=false;available.insert(point->id_);
      out<<'['<<point->id_<<','<<p.x()<<','<<p.y()<<','<<p.z()<<']';if(++count>=10000)break;
     }out<<"],\"keyframes\":[";
     std::vector<std::shared_ptr<stella_vslam::data::keyframe>> keys;
     slam->get_map_publisher()->get_keyframes(keys);
     std::sort(keys.begin(),keys.end(),[](const auto& a,const auto& b){return a->timestamp_<b->timestamp_;});
     first=true;
     const auto start=keys.size()>12?keys.size()-12:0;
     for(size_t i=start;i<keys.size();++i){
      const auto& key=keys[i];auto p=key->get_pose_wc();if(!p.allFinite())continue;
      if(!first)out<<',';first=false;
      out<<"{\"id\":"<<key->id_<<",\"timestamp\":"<<key->timestamp_<<",\"pose\":[";
      for(int r=0;r<4;++r)for(int c=0;c<4;++c){if(r||c)out<<',';out<<p(r,c);}out<<"],\"landmark_ids\":[";
      bool first_id=true;
      for(const auto& point:key->get_valid_landmarks())if(point&&available.count(point->id_)){
       if(!first_id)out<<',';first_id=false;out<<point->id_;
      }out<<"]}";
     }out<<"],\"active_keyframes\":[";
     first=true;
     for(const auto& key:keys){
      if(!first)out<<',';first=false;
      out<<"{\"id\":"<<key->id_<<",\"timestamp\":"<<key->timestamp_<<'}';
     }out<<']';
    }out<<'}';
    std::cout<<out.str()<<'\n'<<std::flush;
   }
  }catch(...){slam->shutdown();throw;}
  slam->shutdown();
  slam->save_map_database((output/"map.msg").string());
  slam->save_frame_trajectory((output/"frame_trajectory.txt").string(),"TUM");
  slam->save_keyframe_trajectory((output/"keyframe_trajectory.txt").string(),"TUM");
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
 return 0;
}
