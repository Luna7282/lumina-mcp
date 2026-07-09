import { Route, Routes } from "react-router-dom";
import Navbar from "./components/layout/Navbar";
import LandingPage from "./pages/LandingPage";
import AnalyzePage from "./pages/AnalyzePage";
import ResultsPage from "./pages/ResultsPage";

export default function App() {
  return (
    <div className="min-h-screen bg-background text-text-primary">
      <Navbar />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/analyze" element={<AnalyzePage />} />
        <Route path="/results/:codebaseId" element={<ResultsPage />} />
      </Routes>
    </div>
  );
}
