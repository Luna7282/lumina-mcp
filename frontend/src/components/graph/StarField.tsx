import { useMemo } from "react";
import * as THREE from "three";

const STAR_COUNT = 200;
const FIELD_RADIUS = 40;

export default function StarField() {
  const geometry = useMemo(() => {
    const positions = new Float32Array(STAR_COUNT * 3);
    for (let i = 0; i < STAR_COUNT; i++) {
      positions[i * 3] = (Math.random() - 0.5) * FIELD_RADIUS;
      positions[i * 3 + 1] = (Math.random() - 0.5) * FIELD_RADIUS;
      positions[i * 3 + 2] = (Math.random() - 0.5) * FIELD_RADIUS;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return geo;
  }, []);

  return (
    <points geometry={geometry}>
      <pointsMaterial color="#ffffff" size={0.05} sizeAttenuation transparent opacity={0.6} />
    </points>
  );
}
