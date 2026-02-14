import { NavLink, Route, Routes } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import QuestionsPage from "./pages/QuestionsPage";

function NavItem({ to, children }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        [
          "rounded-full px-4 py-2 text-sm font-medium transition-colors",
          isActive
            ? "bg-ub-blue text-white"
            : "bg-ub-panel text-ub-muted hover:text-ub-text",
        ].join(" ")
      }
    >
      {children}
    </NavLink>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-ub-bg text-ub-text">
      <header className="border-b border-ub-border bg-[#0D111B]/90 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-4">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-ub-muted">
              Uni-Bot
            </p>
            <h1 className="text-lg font-semibold">Auto Lesson Registration</h1>
          </div>
          <nav className="flex items-center gap-2">
            <NavItem to="/">Main</NavItem>
            <NavItem to="/questions">Q&A</NavItem>
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-5 py-8">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/questions" element={<QuestionsPage />} />
        </Routes>
      </main>
    </div>
  );
}
