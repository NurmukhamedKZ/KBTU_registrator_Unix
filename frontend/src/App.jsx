import { NavLink, Route, Routes } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import QuestionsPage from "./pages/QuestionsPage";

function NavItem({ to, children }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        [
          "ub-btn rounded-full px-4 py-2 text-sm font-medium",
          isActive
            ? "ub-btn-active text-ub-accent"
            : "text-ub-text/70 hover:text-ub-text",
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
      <header className="bg-ub-panel">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-4">
          <div>
            <p className="text-3xl uppercase tracking-[0.18em] text-ub-text/75">
              <span style={{ color: "#2F6CFF" }} className="text-ub-accent">Uni-</span>
              <span style={{ color: "#F58220" }}>Bot</span>
            </p>
            <h1 className="text-lg font-semibold">
              Автоматизация уроков UniX
            </h1>
          </div>
          <nav className="flex items-center gap-2">
            <NavItem to="/">Главная</NavItem>
            <NavItem to="/questions">Вопросы и ответы</NavItem>
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
