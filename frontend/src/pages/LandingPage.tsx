import { Link } from "react-router-dom";
import HeroBackground from "../components/landing/HeroBackground";

const FEATURES = [
  {
    title: "Parse any language",
    icon: (
      <path d="M9 18l-6-6 6-6M15 6l6 6-6 6" />
    ),
    description:
      "Tree-sitter AST extraction for 10+ languages. Python, TypeScript, Go, Rust, Java, and more.",
  },
  {
    title: "Intelligent graph",
    icon: (
      <>
        <circle cx="6" cy="6" r="2.2" />
        <circle cx="18" cy="6" r="2.2" />
        <circle cx="12" cy="18" r="2.2" />
        <path d="M7.7 7.3 10.5 16M16.3 7.3 13.5 16M8.2 6h7.6" />
      </>
    ),
    description:
      "NetworkX + Leiden clustering finds communities and architectural hubs automatically.",
  },
  {
    title: "Animated videos",
    icon: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M10 8.5v7l6-3.5-6-3.5Z" />
      </>
    ),
    description:
      "AI generates Manim scenes explaining your architecture. One video per subsystem.",
  },
];

const STEPS = [
  "Upload your codebase (zip or files)",
  "Lumina builds the dependency graph",
  "AI generates explanation videos",
  "Share with your team",
];

export default function LandingPage() {
  return (
    <main>
      {/* Hero */}
      <section className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-6 pt-14">
        <HeroBackground />

        <div className="relative z-10 flex max-w-3xl flex-col items-center text-center">
          <h1 className="text-balance text-5xl font-bold tracking-tight text-text-primary sm:text-6xl md:text-7xl">
            Understand any codebase{" "}
            <span className="bg-gradient-to-r from-accent via-purple-400 to-blue-400 bg-clip-text text-transparent">
              in minutes
            </span>
          </h1>
          <p className="mt-6 max-w-xl text-balance text-lg text-text-muted">
            Lumina analyzes your code, builds a dependency graph, and
            generates animated explainer videos automatically.
          </p>

          <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row">
            <Link
              to="/analyze"
              className="rounded-lg bg-gradient-to-r from-accent to-purple-600 px-7 py-3 text-sm font-semibold text-white shadow-lg shadow-accent/25 transition-transform hover:scale-[1.03] hover:shadow-accent/40"
            >
              Analyze a repo →
            </Link>
            <a
              href="#features"
              className="rounded-lg border border-border px-7 py-3 text-sm font-semibold text-text-primary transition-colors hover:border-accent hover:text-accent"
            >
              See how it works
            </a>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="mx-auto max-w-6xl px-6 py-24">
        <div className="grid gap-6 sm:grid-cols-3">
          {FEATURES.map((feature) => (
            <div
              key={feature.title}
              className="rounded-xl border border-border bg-surface p-6 transition-colors hover:border-accent/50"
            >
              <svg
                width="28"
                height="28"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="mb-4 text-accent"
              >
                {feature.icon}
              </svg>
              <h3 className="mb-2 text-lg font-semibold text-text-primary">
                {feature.title}
              </h3>
              <p className="text-sm leading-relaxed text-text-muted">
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section className="mx-auto max-w-5xl px-6 py-24">
        <h2 className="mb-16 text-center text-3xl font-bold text-text-primary">
          How it works
        </h2>
        <div className="relative grid gap-10 sm:grid-cols-4">
          <div className="absolute left-0 right-0 top-5 hidden h-px bg-border sm:block" />
          {STEPS.map((step, i) => (
            <div key={step} className="relative flex flex-col items-center text-center">
              <div className="z-10 mb-4 flex h-10 w-10 items-center justify-center rounded-full border border-accent bg-background text-sm font-semibold text-accent">
                {i + 1}
              </div>
              <p className="text-sm text-text-muted">{step}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border px-6 py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 text-sm text-text-muted sm:flex-row">
          <span>Built with manimstudio.me</span>
          <a
            href="https://github.com"
            target="_blank"
            rel="noreferrer"
            className="transition-colors hover:text-text-primary"
          >
            GitHub
          </a>
        </div>
      </footer>
    </main>
  );
}
