import { Canvas } from "@react-three/fiber";
import ParticleField from "./ParticleField";

export default function HeroBackground() {
  return (
    <div className="absolute inset-0 -z-10">
      <Canvas camera={{ position: [0, 0, 9], fov: 55 }} dpr={[1, 1.5]}>
        <ambientLight intensity={0.6} />
        <ParticleField />
      </Canvas>
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-background/40 to-background" />
    </div>
  );
}
