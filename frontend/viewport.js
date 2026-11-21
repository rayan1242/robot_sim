import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';

const CAPACITY = 5000, TRAIL_CAPACITY = 40000;
export class SpatialView {
  constructor(element) {
    this.element = element;
    this.renderer = new THREE.WebGLRenderer({antialias:true, alpha:true});
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1,2));
    this.renderer.setClearColor(0x000000, 0);
    element.appendChild(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(45,1,0.001,1000);
    this.camera.position.set(2,1.5,2);
    this.controls = new OrbitControls(this.camera,this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 0.001;
    this.group = new THREE.Group();
    // OpenCV world convention is displayed through one shared rotation, including poses.
    this.group.rotation.x = Math.PI;
    this.scene.add(this.group);
    this.geometry = new THREE.BufferGeometry();
    this.positions = new Float32Array(CAPACITY*3);
    this.colors = new Float32Array(CAPACITY*3);
    this.geometry.setAttribute('position',new THREE.BufferAttribute(this.positions,3).setUsage(THREE.DynamicDrawUsage));
    this.geometry.setAttribute('color',new THREE.BufferAttribute(this.colors,3).setUsage(THREE.DynamicDrawUsage));
    this.geometry.setDrawRange(0,0);
    this.material = new THREE.PointsMaterial({size:0.01,vertexColors:true,sizeAttenuation:true,transparent:true,opacity:0.9});
    this.points = new THREE.Points(this.geometry,this.material);
    this.points.frustumCulled = false;
    this.group.add(this.points);
    this.trailGeometry = new THREE.BufferGeometry();
    this.trail = new Float32Array(TRAIL_CAPACITY*3);
    this.trailGeometry.setAttribute('position',new THREE.BufferAttribute(this.trail,3).setUsage(THREE.DynamicDrawUsage));
    this.trailGeometry.setDrawRange(0,0);
    this.trailLine = new THREE.LineSegments(this.trailGeometry,new THREE.LineBasicMaterial({color:0xa3f1c5,transparent:true,opacity:0.85}));
    this.trailLine.frustumCulled = false;
    this.group.add(this.trailLine);
    const corners = [[-0.65,-0.45,1],[0.65,-0.45,1],[0.65,0.45,1],[-0.65,0.45,1]];
    const segments = [];
    for(let i=0;i<4;i++) segments.push(0,0,0,...corners[i],...corners[i],...corners[(i+1)%4]);
    const frustumGeometry = new THREE.BufferGeometry();
    frustumGeometry.setAttribute('position',new THREE.Float32BufferAttribute(segments,3));
    this.frustum = new THREE.LineSegments(frustumGeometry,new THREE.LineBasicMaterial({color:0xc5f7d8}));
    this.frustum.visible = false;
    this.group.add(this.frustum);
    this.grid = new THREE.GridHelper(10,40,0x3c5a50,0x23372f);
    this.grid.material.transparent = true;
    this.grid.material.opacity = 0.45;
    this.scene.add(this.grid);
    this.axes = new THREE.AxesHelper(0.2);
    this.axes.material.transparent = true;
    this.axes.material.opacity = 0.6;
    this.group.add(this.axes);
    this.trailCount = 0; this.previousPose = null; this.hasCloud = false;
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(element);
    this.renderer.setAnimationLoop(() => {
      this.controls.update();
      this.renderer.render(this.scene,this.camera);
    });
    this.resize();
  }
  resize() {
    const {clientWidth:w,clientHeight:h}=this.element;
    if(!w || !h) return;
    this.camera.aspect=w/h; this.camera.updateProjectionMatrix(); this.renderer.setSize(w,h,false);
  }
  reset() {
    this.hasCloud=false; this.geometry.setDrawRange(0,0); this.resetTrail();
  }
  resetTrail() { this.trailCount=0; this.previousPose=null; this.trailGeometry.setDrawRange(0,0); this.frustum.visible=false; }
  setCloud(values) {
    const count=Math.min(values.length/6,CAPACITY);
    for(let i=0;i<count;i++) for(let axis=0;axis<3;axis++) {
      this.positions[i*3+axis]=values[i*6+axis];
      this.colors[i*3+axis]=values[i*6+3+axis];
    }
    this.geometry.attributes.position.needsUpdate=true;
    this.geometry.attributes.color.needsUpdate=true;
    this.geometry.setDrawRange(0,count);
    const first=!this.hasCloud; this.hasCloud=count>0; this.count=count;
    if(first && count) this.fit();
  }
  fit() {
    if(!this.hasCloud) return;
    const box=new THREE.Box3();
    for(let i=0;i<this.count;i++) box.expandByPoint(new THREE.Vector3().fromArray(this.positions,i*3));
    this.group.updateMatrixWorld(true); box.applyMatrix4(this.group.matrixWorld);
    const center=box.getCenter(new THREE.Vector3()), size=Math.max(box.getSize(new THREE.Vector3()).length(),0.01);
    this.camera.near=size/1000; this.camera.far=size*1000; this.camera.updateProjectionMatrix();
    this.camera.position.copy(center).add(new THREE.Vector3(1,0.65,1.4).normalize().multiplyScalar(size*1.25));
    this.controls.target.copy(center); this.controls.maxDistance=size*100;
    this.controls.update(); this.material.size=size*0.004;
    this.frustum.scale.setScalar(size*0.045);
    this.axes.scale.setScalar(size*0.4);
    this.grid.scale.setScalar(size/5);
  }
  setPose(pose) {
    if(!Array.isArray(pose) || pose.length!==7 || !pose.every(Number.isFinite)) {this.previousPose=null;this.frustum.visible=false;return;}
    this.frustum.position.set(...pose.slice(0,3));
    this.frustum.quaternion.set(...pose.slice(3)).normalize();
    this.frustum.visible=true;
    if(this.previousPose && this.trailCount+2<=TRAIL_CAPACITY) {
      this.trail.set(this.previousPose,this.trailCount*3);
      this.trail.set(pose.slice(0,3),(this.trailCount+1)*3);
      this.trailCount+=2;
      this.trailGeometry.attributes.position.needsUpdate=true;
      this.trailGeometry.setDrawRange(0,this.trailCount);
    }
    this.previousPose=pose.slice(0,3);
  }
  showGrid(value) {this.grid.visible=value;}
  showTrail(value) {this.trailLine.visible=value;}
}
