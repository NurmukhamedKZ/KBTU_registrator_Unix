import { useEffect, useState } from "react";
import { getQuestions } from "../api";

const LIMIT = 20;

function formatDate(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

export default function QuestionsPage() {
  const [questions, setQuestions] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    loadQuestions(page);
  }, [page]);

  async function loadQuestions(pageNumber) {
    setLoading(true);
    setError("");
    try {
      const data = await getQuestions(LIMIT, pageNumber * LIMIT);
      setQuestions(data.questions || []);
      setTotal(data.total || 0);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-2xl border border-ub-border bg-ub-panel p-6 shadow-ub">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold">Questions and answers</h2>
          <p className="mt-1 text-sm text-ub-muted">Total: {total}</p>
        </div>
        <a
          href="/api/questions/export/csv"
          download="questions.csv"
          className="rounded-lg bg-ub-green px-4 py-2 text-sm font-medium text-white"
        >
          Download CSV
        </a>
      </div>

      {error ? (
        <p className="mt-4 rounded-lg border border-ub-danger/30 bg-ub-danger/10 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="mt-6 text-ub-muted">Loading...</p>
      ) : questions.length === 0 ? (
        <p className="mt-6 text-ub-muted">No saved questions yet.</p>
      ) : (
        <div className="mt-6 space-y-4">
          {questions.map((question) => (
            <article
              key={question.id}
              className="rounded-xl border border-ub-border bg-ub-panelSoft p-4"
            >
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs text-ub-muted">#{question.id}</span>
                <span className="text-xs text-ub-muted">{formatDate(question.created_at)}</span>
              </div>

              <h3 className="text-base font-semibold">{question.question_text}</h3>

              <p className="mt-1 text-xs text-ub-muted">
                {question.lesson_name || "Unknown lesson"}
                {question.user_email ? ` • ${question.user_email}` : ""}
              </p>

              <div className="mt-3 space-y-2">
                {(question.answers || []).map((answer, idx) => (
                  <div
                    key={`${question.id}-${idx}`}
                    className={[
                      "rounded-lg border px-3 py-2 text-sm",
                      answer.is_selected
                        ? "border-ub-blue/40 bg-ub-blue/15 text-blue-200"
                        : "border-ub-border bg-ub-bg text-ub-text",
                    ].join(" ")}
                  >
                    <span className="mr-2 text-xs text-ub-muted">{idx + 1}.</span>
                    {answer.text}
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
      )}

      <div className="mt-6 flex items-center justify-center gap-3">
        <button
          type="button"
          disabled={page === 0}
          onClick={() => setPage((prev) => Math.max(0, prev - 1))}
          className="rounded-lg border border-ub-border px-3 py-2 text-sm text-ub-muted disabled:opacity-40"
        >
          Previous
        </button>
        <span className="text-sm text-ub-muted">Page {page + 1}</span>
        <button
          type="button"
          disabled={(page + 1) * LIMIT >= total}
          onClick={() => setPage((prev) => prev + 1)}
          className="rounded-lg border border-ub-border px-3 py-2 text-sm text-ub-muted disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </section>
  );
}
