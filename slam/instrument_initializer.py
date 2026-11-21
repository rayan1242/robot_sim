"""Add opt-in diagnostics to the local SLAM build copy, preserving decision logic."""
import argparse
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    a=p.parse_args()
    path=a.source/'src/stella_vslam/initialize/base.cc'
    text=path.read_text()
    marker='ROBOT_INITIALIZER_DIAGNOSTICS'
    if marker in text:
        print('Initializer diagnostics already present')
        return
    anchor='    rot_ref_to_cur_ = Mat33_t::Zero();'
    if text.count(anchor)!=1:raise ValueError('Unexpected pinned initializer source')
    addition='''    // Observational only: report the actual initializer hypotheses before gates.
    if (std::getenv("ROBOT_INITIALIZER_DIAGNOSTICS")) {
        for (unsigned int i = 0; i < num_hypothesis; ++i) {
            spdlog::info("INITIALIZER_CANDIDATE index={} valid={} triangulated={} parallax_deg={} required_valid={} required_triangulated={} required_parallax_deg={}",
                         i, nums_valid_pts.at(i), num_triangulated_pts.at(i),
                         std::acos(std::max(-1.0f, std::min(1.0f, init_parallax.at(i)))) * 180.0 / M_PI,
                         min_num_valid_pts_, min_num_triangulated_, parallax_deg_thr_);
        }
    }

'''
    text='#include <cstdlib>\n#include <spdlog/spdlog.h>\n'+text.replace(anchor,addition+anchor)
    path.write_text(text)
    print('Instrumented actual initializer hypotheses; gates unchanged')


if __name__=='__main__':main()
