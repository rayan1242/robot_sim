// RGB-only TUM runner: no depth image association, no viewer, and exact RGB timestamps.
#include <stella_vslam/config.h>
#include <stella_vslam/system.h>
#include <stella_vslam/publish/map_publisher.h>
#include <stella_vslam/data/landmark.h>
#include <stella_vslam/data/keyframe.h>
#include <opencv2/imgcodecs.hpp>
#include <Eigen/Geometry>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <set>
#include <sstream>
#include <thread>

int main(int argc, char** argv) {
    if (argc != 5) {
        std::cerr << "Usage: run_mono_dataset CONFIG VOCAB DATASET OUTPUT\n";
        return 1;
    }
    try {
        const auto dataset = std::filesystem::canonical(argv[3]);
        const std::filesystem::path output(argv[4]);
        std::filesystem::create_directories(output);
        auto config = std::make_shared<stella_vslam::config>(argv[1]);
        auto slam = std::make_shared<stella_vslam::system>(config, argv[2]);
        std::ifstream index(dataset / "rgb.txt");
        if (!index) throw std::runtime_error("Cannot open rgb.txt");
        std::ofstream tracking(output / "tracking.csv");
        tracking << "timestamp,pose_available,tracking_ms\n" << std::setprecision(15);
        slam->startup();
        unsigned int count = 0;
        try {
            std::string line;
            while (std::getline(index, line)) {
                if (line.empty() || line[0] == '#') continue;
                double timestamp;
                std::string filename;
                std::istringstream row(line);
                if (!(row >> timestamp >> filename)) throw std::runtime_error("Malformed RGB index");
                auto relative = std::filesystem::path(filename);
                if (relative.is_absolute()) throw std::runtime_error("Absolute dataset path rejected");
                for (const auto& part : relative) {
                    if (part == "..") throw std::runtime_error("Dataset path traversal rejected");
                }
                auto image = cv::imread((dataset / relative).string(), cv::IMREAD_COLOR);
                if (image.empty() || image.cols != 640 || image.rows != 480)
                    throw std::runtime_error("Expected 640x480 RGB frame: " + filename);
                const auto start = std::chrono::steady_clock::now();
                auto pose = slam->feed_monocular_frame(image, timestamp);
                const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now()-start).count();
                tracking << timestamp << ',' << (pose ? 1 : 0) << ',' << ms << '\n';
                if (++count % 100 == 0) std::cout << "Processed " << count << " frames\n" << std::flush;
            }
            // Match the upstream example: wait for active loop BA before shutdown.
            while (slam->loop_BA_is_running()) std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        catch (...) {
            slam->shutdown();
            throw;
        }
        slam->shutdown();
        slam->save_frame_trajectory((output / "frame_trajectory.txt").string(), "TUM");
        slam->save_keyframe_trajectory((output / "keyframe_trajectory.txt").string(), "TUM");
        if (!slam->save_map_database((output / "map.msg").string()))
            throw std::runtime_error("Map database save failed");
        std::vector<std::shared_ptr<stella_vslam::data::landmark>> landmarks;
        std::set<std::shared_ptr<stella_vslam::data::landmark>> local;
        slam->get_map_publisher()->get_landmarks(landmarks, local);
        std::ofstream points(output / "landmarks.csv");
        points << "id,x,y,z,observations\n" << std::setprecision(15);
        for (const auto& point : landmarks) {
            if (!point || point->will_be_erased()) continue;
            const auto position = point->get_pos_in_world();
            points << point->id_ << ',' << position.x() << ',' << position.y() << ',' << position.z()
                   << ',' << point->num_observations() << '\n';
        }
        std::vector<std::shared_ptr<stella_vslam::data::keyframe>> keyframes;
        slam->get_map_publisher()->get_keyframes(keyframes);
        std::ofstream observations(output / "observations.csv");
        observations << "keyframe_id,timestamp,landmark_id\n" << std::setprecision(15);
        for (const auto& keyframe : keyframes) {
            for (const auto& point : keyframe->get_valid_landmarks()) {
                if (point && !point->will_be_erased())
                    observations << keyframe->id_ << ',' << keyframe->timestamp_ << ',' << point->id_ << '\n';
            }
        }
        std::cout << "Saved " << count << " input frames, " << keyframes.size() << " keyframes, "
                  << landmarks.size() << " landmarks\n";
    }
    catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
