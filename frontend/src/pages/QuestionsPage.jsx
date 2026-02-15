import { useEffect, useState } from "react";
import { downloadQuestionsCsv, getQuestions } from "../api";

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
  const [downloadingCsv, setDownloadingCsv] = useState(false);
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

  async function handleDownloadCsv() {
    setError("");
    setDownloadingCsv(true);
    try {
      const blob = await downloadQuestionsCsv();
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = "questions.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(blobUrl);
    } catch (e) {
      setError(e.message);
    } finally {
      setDownloadingCsv(false);
    }
  }

  return (
    <section className="rounded-2xl bg-ub-panel p-6 shadow-ub">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold">Вопросы и ответы</h2>
          <p className="mt-1 text-sm text-ub-text/70">Всего: {total}</p>
        </div>
        <button
          type="button"
          onClick={handleDownloadCsv}
          disabled={downloadingCsv}
          className="ub-btn rounded-lg px-4 py-2 text-sm font-medium text-white"
        >
          {downloadingCsv ? "Скачивание..." : "Скачать CSV"}
        </button>
      </div>

      {error ? (
        <p className="mt-4 rounded-lg bg-ub-control px-3 py-2 text-sm text-ub-text">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="mt-6 text-ub-text/70">Загрузка...</p>
      ) : questions.length === 0 ? (
        <p className="mt-6 text-ub-text/70">Сохраненных вопросов пока нет.</p>
      ) : (
        <div className="mt-6 space-y-4">
          {questions.map((question) => (
            <article
              key={question.id}
              className="rounded-xl bg-ub-control p-4"
            >
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs text-ub-text/70">#{question.id}</span>
                <span className="text-xs text-ub-text/70">{formatDate(question.created_at)}</span>
              </div>

              <h3 className="text-base font-semibold">{question.question_text}</h3>

              <p className="mt-1 text-xs text-ub-text/70">
                {question.lesson_name || "Неизвестный урок"}
                {question.user_email ? ` • ${question.user_email}` : ""}
              </p>

              <div className="mt-3 space-y-2">
                {(question.answers || []).map((answer, idx) => (
                  <div
                    key={`${question.id}-${idx}`}
                    className={[
                      "rounded-lg px-3 py-2 text-sm",
                      answer.is_selected
                        ? "bg-ub-accent/20 text-ub-text"
                        : "bg-ub-panel text-ub-text",
                    ].join(" ")}
                  >
                    <span className="mr-2 text-xs text-ub-text/70">{idx + 1}.</span>
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
          className="ub-btn rounded-lg px-3 py-2 text-sm text-ub-text/70 disabled:opacity-40"
        >
          Назад
        </button>
        <span className="text-sm text-ub-text/70">Страница {page + 1}</span>
        <button
          type="button"
          disabled={(page + 1) * LIMIT >= total}
          onClick={() => setPage((prev) => prev + 1)}
          className="ub-btn rounded-lg px-3 py-2 text-sm text-ub-text/70 disabled:opacity-40"
        >
          Далее
        </button>
      </div>
    </section>
  );
}
