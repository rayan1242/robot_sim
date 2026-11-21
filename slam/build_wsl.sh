#!/usr/bin/env bash
# Run after installing the packages listed in slam/README.md.
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
build_root="${SLAM_BUILD_ROOT:-$HOME/robot_sim_slam}"
install_root="$build_root/install"
mkdir -p "$build_root/src" "$install_root"
for project in g2o stella_vslam; do
  if [ ! -d "$build_root/src/$project" ]; then
    cp -a "$repo_root/.cache/slam-source/$project" "$build_root/src/$project"
  fi
done
cmake -S "$build_root/src/g2o" -B "$build_root/build/g2o" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$install_root" \
  -DBUILD_SHARED_LIBS=ON -DBUILD_UNITTESTS=OFF -DG2O_USE_CHOLMOD=OFF \
  -DG2O_USE_CSPARSE=ON -DG2O_USE_OPENGL=OFF -DG2O_USE_OPENMP=OFF \
  -DG2O_BUILD_APPS=OFF -DG2O_BUILD_EXAMPLES=OFF -DG2O_BUILD_LINKED_APPS=OFF
cmake --build "$build_root/build/g2o" --parallel 2
cmake --install "$build_root/build/g2o"
cmake -S "$build_root/src/stella_vslam/3rd/FBoW" -B "$build_root/build/fbow" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$install_root" -DBUILD_UTILS=OFF
cmake --build "$build_root/build/fbow" --parallel 2
cmake --install "$build_root/build/fbow"
# Modern Ubuntu's fmt dependency requires C++17 (also used by upstream's modern Dockerfile).
sed -i 's/set(CMAKE_CXX_STANDARD 11)/set(CMAKE_CXX_STANDARD 17)/' "$build_root/src/stella_vslam/CMakeLists.txt"
cmake -S "$build_root/src/stella_vslam" -B "$build_root/build/stella" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$install_root" \
  -DCMAKE_PREFIX_PATH="$install_root" -DBUILD_TESTS=OFF -DUSE_ARUCO=OFF
cmake --build "$build_root/build/stella" --parallel 2
cmake --install "$build_root/build/stella"
cmake -S "$repo_root/slam" -B "$build_root/build/runner" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$install_root"
cmake --build "$build_root/build/runner" --parallel 2
printf 'Ready: %s/build/runner/run_mono_dataset\n' "$build_root"
