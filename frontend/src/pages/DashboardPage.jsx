import { useEffect, useMemo, useRef, useState } from "react";
import {
  getAgentLogs,
  getAgentStatus,
  startBatchAgent,
  startSingleAgent,
  stopAgent,
} from "../api";

const SESSION_KEY = "agent_session_id";
const EMAIL_KEY = "unix_email";

function classNames(...items) {
  return items.filter(Boolean).join(" ");
}

export default function DashboardPage() {
  const [mode, setMode] = useState("single");
  const [sessionId, setSessionId] = useState(localStorage.getItem(SESSION_KEY) || "");
  const [unixEmail, setUnixEmail] = useState(localStorage.getItem(EMAIL_KEY) || "");
  const [unixPassword, setUnixPassword] = useState("");
  const [lessonId, setLessonId] = useState("");
  const [skipVideo, setSkipVideo] = useState(false);
  const [batchLessonIds, setBatchLessonIds] = useState("");
  const [batchSkipVideo, setBatchSkipVideo] = useState(false);
  const [agentStatus, setAgentStatus] = useState({
    running: false,
    current_lesson: null,
    last_run: null,
    log_count: 0,
  });
  const [logs, setLogs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [wasRunning, setWasRunning] = useState(false);
  const logsRef = useRef(null);
  const shouldAutoScrollRef = useRef(true);

  const safeStatus = agentStatus || {
    running: false,
    current_lesson: null,
    last_run: null,
    log_count: 0,
  };

  const canStartSingle = unixEmail && unixPassword && lessonId && !safeStatus.running && !busy;
  const canStartBatch =
    unixEmail && unixPassword && batchLessonIds && !safeStatus.running && !busy;

  useEffect(() => {
    const timer = window.setInterval(() => {
      refreshStatus();
    }, 1500);
    refreshStatus();
    return () => window.clearInterval(timer);
  }, [sessionId, wasRunning]);

  useEffect(() => {
    if (logsRef.current && shouldAutoScrollRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  }, [logs]);

  function handleLogsScroll() {
    const container = logsRef.current;
    if (!container) return;

    const distanceToBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldAutoScrollRef.current = distanceToBottom < 24;
  }

  async function refreshStatus() {
    try {
      const status = await getAgentStatus(sessionId);
      const normalizedStatus = status || {
        running: false,
        current_lesson: null,
        last_run: null,
        log_count: 0,
      };
      setAgentStatus(normalizedStatus);
      if ((normalizedStatus.running || normalizedStatus.log_count > 0) && sessionId) {
        const lines = await getAgentLogs(sessionId);
        setLogs(lines);
      }
      if (wasRunning && !normalizedStatus.running) {
        setWasRunning(false);
      }
    } catch (e) {
      setError(e.message);
    }
  }

  async function tryStoreCredentials() {
    try {
      if ("credentials" in navigator && "PasswordCredential" in window) {
        const credential = new window.PasswordCredential({
          id: unixEmail.trim(),
          password: unixPassword,
          name: unixEmail.trim(),
        });
        await navigator.credentials.store(credential);
      }
    } catch {
      // Browser may block this API; autocomplete still works as fallback.
    }
  }

  async function handleStartSingle() {
    if (!canStartSingle) return;
    setBusy(true);
    setError("");
    try {
      localStorage.setItem(EMAIL_KEY, unixEmail);
      await tryStoreCredentials();
      const data = await startSingleAgent({
        lesson_id: lessonId.trim(),
        skip_video: skipVideo,
        unix_email: unixEmail.trim(),
        unix_password: unixPassword,
      });
      setSessionId(data.session_id);
      localStorage.setItem(SESSION_KEY, data.session_id);
      setWasRunning(true);
      shouldAutoScrollRef.current = true;
      setLogs([]);
      await refreshStatus();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleStartBatch() {
    if (!canStartBatch) return;
    setBusy(true);
    setError("");
    try {
      localStorage.setItem(EMAIL_KEY, unixEmail);
      await tryStoreCredentials();
      const data = await startBatchAgent({
        lesson_ids: batchLessonIds.trim(),
        skip_video: batchSkipVideo,
        unix_email: unixEmail.trim(),
        unix_password: unixPassword,
      });
      setSessionId(data.session_id);
      localStorage.setItem(SESSION_KEY, data.session_id);
      setWasRunning(true);
      shouldAutoScrollRef.current = true;
      setLogs([]);
      await refreshStatus();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleStop() {
    if (!sessionId || !safeStatus.running || busy) return;
    setBusy(true);
    setError("");
    try {
      await stopAgent(sessionId);
      await refreshStatus();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const statusColor = useMemo(
    () => (safeStatus.running ? "bg-ub-accent/20 text-ub-text" : "bg-ub-control text-ub-text/70"),
    [safeStatus.running]
  );

  return (
    <div className="space-y-6">
      <section className="rounded-2xl bg-ub-panel p-6 shadow-ub">
        <h2 className="text-2xl font-bold">Главная страница</h2>
        <p className="mt-1 text-sm text-ub-text/70">
          Короткая инструкция по запуску бота.
        </p>
        <div className="mt-4 p-1 text-sm text-ub-text/70">
          <p>1) Выберите режим: одна лекция или несколько лекций.</p>
          <p>2) Введите UniX email и пароль. (мы не сохраняем ваши пароли)</p>
          <p>3) Укажите ID/URL урока или список ID и нажмите «Запустить». (ID можно найти в URL(ссылке) урока)</p>
          <p>4) Делайте свои дела, пока бот проходит уроки и делает тесты.</p>
          <p>5) После завершения тестов, бот сохранит вопросы и ответы в Базе данных.</p>
        </div>
      </section>

      <section className="rounded-2xl bg-ub-panel p-6 shadow-ub">
        
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setMode("single")}
            className={classNames(
              "ub-btn rounded-full px-4 py-2 text-sm font-medium",
              mode === "single" ? "ub-btn-active text-ub-accent" : "text-ub-text/70"
            )}
          >
            Одна лекция
          </button>
          <button
            type="button"
            onClick={() => setMode("batch")}
            className={classNames(
              "ub-btn rounded-full px-4 py-2 text-sm font-medium",
              mode === "batch" ? "ub-btn-active text-ub-accent" : "text-ub-text/70"
            )}
          >
            Несколько лекций
          </button>
        </div>

        <div className="mb-4 grid gap-4 md:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block text-ub-text/70">Email UniX</span>
            <input
              name="username"
              autoComplete="username"
              type="email"
              value={unixEmail}
              onChange={(e) => setUnixEmail(e.target.value)}
              className="ub-input w-full rounded-lg px-3 py-2 outline-none ring-0 transition"
              placeholder="your@kbtu.kz"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-ub-text/70">Password UniX</span>
            <input
              name="password"
              autoComplete="current-password"
              type="password"
              value={unixPassword}
              onChange={(e) => setUnixPassword(e.target.value)}
              className="ub-input w-full rounded-lg px-3 py-2 outline-none ring-0 transition"
              placeholder="********"
            />
          </label>
        </div>

        {mode === "single" ? (
          <div className="grid gap-4 md:grid-cols-[1fr_auto_auto]">
            <label className="text-sm">
              <span className="mb-1 block text-ub-text/70">ID урока или URL</span>
              <input
                type="text"
                value={lessonId}
                onChange={(e) => setLessonId(e.target.value)}
                className="ub-input w-full rounded-lg px-3 py-2 outline-none transition"
                placeholder="191 или https://uni-x.almv.kz/platform/lessons/191"
              />
            </label>
            {/* <label className="flex items-center gap-2 text-sm text-ub-text/70">
              <input
                type="checkbox"
                checked={skipVideo}
                onChange={(e) => setSkipVideo(e.target.checked)}
              />

              Пропустить видео
            </label> */}
            <button
              type="button"
              disabled={!canStartSingle}
              onClick={handleStartSingle}
              className="ub-btn rounded-lg px-4 py-2 font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              Запустить
            </button>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-[1fr_auto_auto]">
            <label className="text-sm">
              <span className="mb-1 block text-ub-text/70">ID уроков (через запятую)</span>
              <input
                type="text"
                value={batchLessonIds}
                onChange={(e) => setBatchLessonIds(e.target.value)}
                className="ub-input w-full rounded-lg px-3 py-2 outline-none transition"
                placeholder="9843, 9845, 9910"
              />
            </label>
            {/* <label className="flex items-center gap-2 text-sm text-ub-text/70">
              <input
                type="checkbox"
                checked={batchSkipVideo}
                onChange={(e) => setBatchSkipVideo(e.target.checked)}
              />
              
            </label> */}
            <button
              type="button"
              disabled={!canStartBatch}
              onClick={handleStartBatch}
              className="ub-btn rounded-lg px-4 py-2 font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              Запустить
            </button>
          </div>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-3 text-sm">
          <span className={classNames("rounded-full px-3 py-1", statusColor)}>
            {safeStatus.running ? "Запущен" : "Ожидание"}
          </span>
          {safeStatus.current_lesson ? (
            <span className="text-ub-text/70">{safeStatus.current_lesson}</span>
          ) : null}
          {sessionId ? <span className="text-xs text-ub-text/70">Сессия: {sessionId}</span> : null}
          <button
            type="button"
            onClick={handleStop}
            disabled={!safeStatus.running || busy}
            className="ub-btn ml-auto rounded-lg px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            Остановить
          </button>
        </div>

        {error ? (
          <p className="mt-4 rounded-lg bg-ub-control px-3 py-2 text-sm text-ub-text">
            {error}
          </p>
        ) : null}
      </section>

      <section className="rounded-2xl bg-ub-panel p-6 shadow-ub">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-semibold">Логи агента</h3>
          <button
            type="button"
            onClick={() => {
              shouldAutoScrollRef.current = true;
              setLogs([]);
            }}
            className="ub-btn rounded-lg px-3 py-1 text-xs text-ub-text/70 hover:text-ub-text"
          >
            Очистить
          </button>
        </div>
        <div
          ref={logsRef}
          onScroll={handleLogsScroll}
          className="h-72 overflow-y-auto rounded-xl bg-ub-bg p-3 font-mono text-xs text-ub-text"
        >
          {logs.length === 0 ? (
            <p className="text-ub-text/70">Логи пока пустые.</p>
          ) : (
            logs.map((line, idx) => <p key={`${line}-${idx}`}>{line}</p>)
          )}
        </div>
      </section>
    </div>
  );
}
