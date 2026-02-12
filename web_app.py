"""
FastAPI Web Interface for UniX Agent

Provides a web UI to:
- View stored questions and answers
- Start the agent to process lessons
- Monitor agent status
- Supports multiple concurrent users (multi-session)
"""

import csv
import io
import os
import subprocess
import threading
import time
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db_models import DatabaseManager

load_dotenv()

app = FastAPI(title="UniX Agent Dashboard", version="2.0.0")

# Multi-session agent state: session_id -> session_data
agent_sessions: Dict[str, Dict[str, Any]] = {}
sessions_lock = threading.Lock()
MAX_CONCURRENT_AGENTS = int(os.getenv("MAX_CONCURRENT_AGENTS", "5"))


def _create_session(mode: str = "single") -> str:
    """Create a new session, returns session_id."""
    with sessions_lock:
        if sum(1 for s in agent_sessions.values() if s.get("running")) >= MAX_CONCURRENT_AGENTS:
            raise HTTPException(
                status_code=503,
                detail=f"Maximum {MAX_CONCURRENT_AGENTS} agents running. Try again later."
            )
        session_id = str(uuid.uuid4())[:8]
        agent_sessions[session_id] = {
            "running": True,
            "current_lesson": None,
            "mode": mode,
            "logs": [],
            "last_run": None,
            "process": None,
            "created_at": datetime.now().isoformat(),
        }
        return session_id



# Database manager
db_manager = None

def get_db():
    global db_manager
    if db_manager is None:
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            db_manager = DatabaseManager(database_url)
    return db_manager


class LessonRequest(BaseModel):
    lesson_id: str
    skip_video: bool = True
    unix_email: str = ""
    unix_password: str = ""


class BatchRequest(BaseModel):
    """Comma-separated lesson IDs, e.g. '9843, 9845, 9910'"""
    lesson_ids: str
    skip_video: bool = False
    unix_email: str = ""
    unix_password: str = ""


class StopRequest(BaseModel):
    session_id: str = ""


class AgentStatus(BaseModel):
    running: bool
    current_lesson: Optional[str]
    last_run: Optional[str]
    log_count: int
    session_id: Optional[str] = None


def _run_agent_impl(session_id: str, lesson_id: str, skip_video: bool, unix_email: str, unix_password: str):
    """Run the agent in a background thread for a specific session."""
    session = agent_sessions.get(session_id)
    if not session:
        return
    
    session["running"] = True
    session["current_lesson"] = lesson_id
    session["mode"] = "single"
    session["logs"] = []
    session["process"] = None
    
    try:
        lesson_url = f"https://uni-x.almv.kz/platform/lessons/{lesson_id}"
        cmd = ["python3", "unix_agent.py", "--lesson", lesson_url]
        if skip_video:
            cmd.append("--skip-video")
        
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Starting agent for lesson {lesson_id}...")
        
        env = os.environ.copy()
        env["UNIX_EMAIL"] = unix_email
        env["UNIX_PASSWORD"] = unix_password
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
        session["process"] = process
        
        for line in iter(process.stdout.readline, ''):
            if line:
                session["logs"].append(line.strip())
                if len(session["logs"]) > 200:
                    session["logs"] = session["logs"][-200:]
            if process.poll() is not None:
                break
        
        process.wait()
        exit_code = process.returncode
        if exit_code in (-9, -15):
            session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ⛔ Agent stopped by user")
        else:
            session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Agent finished with exit code {exit_code}")
        
    except Exception as e:
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {str(e)}")
    finally:
        session["running"] = False
        session["process"] = None
        session["last_run"] = datetime.now().isoformat()


def _run_batch_agent_impl(session_id: str, lesson_ids: str, skip_video: bool, unix_email: str, unix_password: str):
    """Run batch agent: one process, one browser, same logic as single mode in a loop."""
    import re
    session = agent_sessions.get(session_id)
    if not session:
        return
    
    ids = [x.strip() for x in lesson_ids.split(",") if x.strip()]
    if not ids:
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ No valid lesson IDs provided")
        session["running"] = False
        return
    
    session["running"] = True
    session["current_lesson"] = f"Batch: {len(ids)} lessons ({ids[0]}...)"
    session["mode"] = "batch"
    session["logs"] = []
    session["process"] = None
    
    try:
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Starting BATCH mode: {len(ids)} lessons (one browser session)")
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] IDs: {', '.join(ids)}")
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Skip video: {skip_video}")
        
        env = os.environ.copy()
        env["UNIX_EMAIL"] = unix_email
        env["UNIX_PASSWORD"] = unix_password
        
        cmd = ["python3", "unix_agent.py", "--lesson-ids", lesson_ids]
        if skip_video:
            cmd.append("--skip-video")
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
        session["process"] = process
        
        for line in iter(process.stdout.readline, ''):
            if line:
                line_stripped = line.strip()
                if "Processing lesson" in line_stripped:
                    match = re.search(r'Processing lesson (\d+).*?\((\d+)/(\d+)\)', line_stripped)
                    if match:
                        session["current_lesson"] = f"Lesson {match.group(1)} ({match.group(2)}/{match.group(3)})"
                    else:
                        m = re.search(r'Processing lesson (\d+)', line_stripped)
                        if m:
                            session["current_lesson"] = f"Lesson {m.group(1)}"
                session["logs"].append(line_stripped)
                if len(session["logs"]) > 500:
                    session["logs"] = session["logs"][-500:]
            if process.poll() is not None:
                break
        
        process.wait()
        exit_code = process.returncode
        session["process"] = None
        
        if exit_code in (-9, -15):
            session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ⛔ Batch stopped by user")
        else:
            session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] 🏁 Batch complete")
        
    except Exception as e:
        session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Error: {str(e)}")
    finally:
        session["running"] = False
        session["process"] = None
        session["last_run"] = datetime.now().isoformat()


@app.get("/", response_class=HTMLResponse)
async def home():
    """Serve the main dashboard."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UniX Agent Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js" defer></script>
    <style>
        [x-cloak] { display: none !important; }
        .log-container { font-family: 'Monaco', 'Menlo', monospace; font-size: 12px; }
    </style>
</head>
<body class="bg-gray-100 min-h-screen" x-data="dashboard()">
    <div class="container mx-auto px-4 py-8 max-w-6xl">
        <!-- Header -->
        <div class="bg-white rounded-lg shadow-md p-6 mb-6">
            <h1 class="text-3xl font-bold text-gray-800 mb-2">UniX Agent Dashboard</h1>
            <p class="text-gray-600">Manage your automated lesson processing and view saved questions</p>
        </div>

        <!-- Agent Control Panel -->
        <div class="bg-white rounded-lg shadow-md p-6 mb-6">
            <h2 class="text-xl font-semibold text-gray-800 mb-4">Agent Control</h2>
            
            <!-- UniX Credentials - not stored, used only for login -->
            <div class="mb-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
                <p class="text-sm text-gray-600 mb-2">UniX credentials (not saved, used only for agent login)</p>
                <div class="flex flex-wrap gap-4">
                    <div class="flex-1 min-w-[200px]">
                        <label class="block text-sm font-medium text-gray-700 mb-1">UniX Email</label>
                        <input 
                            type="email" 
                            x-model="unixEmail" 
                            placeholder="your@kbtu.kz"
                            class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            :disabled="agentStatus.running"
                        >
                    </div>
                    <div class="flex-1 min-w-[200px]">
                        <label class="block text-sm font-medium text-gray-700 mb-1">UniX Password</label>
                        <input 
                            type="password" 
                            x-model="unixPassword" 
                            placeholder="••••••••"
                            class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            :disabled="agentStatus.running"
                        >
                    </div>
                </div>
            </div>
            
            <!-- Mode Tabs -->
            <div class="flex border-b border-gray-200 mb-4">
                <button 
                    @click="mode = 'single'"
                    :class="mode === 'single' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'"
                    class="py-2 px-4 border-b-2 font-medium text-sm transition-colors"
                >
                    Single Lesson
                </button>
                <button 
                    @click="mode = 'batch'"
                    :class="mode === 'batch' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'"
                    class="py-2 px-4 border-b-2 font-medium text-sm transition-colors"
                >
                    Batch Mode (All Lessons)
                </button>
            </div>
            
            <!-- Single Lesson Mode -->
            <div x-show="mode === 'single'" class="flex flex-wrap gap-4 items-end">
                <div class="flex-1 min-w-[200px]">
                    <label class="block text-sm font-medium text-gray-700 mb-1">Lesson ID</label>
                    <input 
                        type="text" 
                        x-model="lessonId" 
                        placeholder="https://uni-x.almv.kz/platform/lessons/191 | нужно написать только id (191)"
                        class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        :disabled="agentStatus.running"
                    >
                </div>
                
                <div class="flex items-center gap-2">
                    <input type="checkbox" x-model="skipVideo" id="skipVideo" class="rounded">
                    <label for="skipVideo" class="text-sm text-gray-700">Skip Video</label>
                </div>
                
                <button 
                    @click="startAgent()"
                    :disabled="agentStatus.running || !lessonId || !unixEmail || !unixPassword"
                    class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                >
                    Start Agent
                </button>
            </div>
            
            <!-- Batch Mode -->
            <div x-show="mode === 'batch'" class="space-y-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Lesson IDs (comma-separated) *</label>
                    <input 
                        type="text" 
                        x-model="batchLessonIds" 
                        placeholder="e.g., 9843, 9845, 9910, 9920"
                        class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        :disabled="agentStatus.running"
                    >
                </div>
                
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <input type="checkbox" x-model="batchSkipVideo" id="batchSkipVideo" class="rounded">
                        <label for="batchSkipVideo" class="text-sm text-gray-700">Skip Videos (test only)</label>
                    </div>
                    
                    <button 
                        @click="startBatchAgent()"
                        :disabled="agentStatus.running || !batchLessonIds || !unixEmail || !unixPassword"
                        class="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clip-rule="evenodd" />
                        </svg>
                        Start Batch
                    </button>
                </div>
                
                <div class="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
                    <strong>Batch Mode:</strong> Enter lesson IDs separated by commas. One browser session processes all lessons in sequence 
                    (same logic as single mode). Login once, then each lesson: video → test → next.
                </div>
            </div>
            
            <!-- Status Badge -->
            <div class="mt-4 flex items-center gap-2 flex-wrap">
                <span class="text-sm text-gray-600">Status:</span>
                <span 
                    :class="agentStatus.running ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'"
                    class="px-3 py-1 rounded-full text-sm font-medium"
                >
                    <span x-show="!agentStatus.running">Idle</span>
                    <span x-show="agentStatus.running" class="flex items-center gap-2">
                        <svg class="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                        </svg>
                        Running
                    </span>
                </span>
                <span x-show="agentStatus.current_lesson" class="text-sm text-gray-600">
                    - <span x-text="agentStatus.current_lesson" class="font-medium"></span>
                </span>
                <span x-show="sessionId" class="text-xs text-gray-400">Session: <span x-text="sessionId"></span></span>
                
                <!-- Stop Button -->
                <button 
                    x-show="agentStatus.running"
                    @click="stopAgent()"
                    :disabled="stopping"
                    class="ml-auto px-4 py-1.5 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 disabled:bg-red-400 transition-colors flex items-center gap-2"
                >
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a1 1 0 00-1 1v4a1 1 0 001 1h4a1 1 0 001-1V8a1 1 0 00-1-1H8z" clip-rule="evenodd" />
                    </svg>
                    <span x-text="stopping ? 'Stopping...' : 'Stop Agent'"></span>
                </button>
            </div>
            
            <!-- Logs -->
            <div x-show="logs.length > 0" class="mt-4">
                <div class="flex justify-between items-center mb-2">
                    <h3 class="text-sm font-medium text-gray-700">Agent Logs</h3>
                    <button @click="logs = []" class="text-xs text-gray-500 hover:text-gray-700">Clear</button>
                </div>
                <div class="bg-gray-900 text-green-400 p-4 rounded-lg h-64 overflow-y-auto log-container" x-ref="logContainer">
                    <template x-for="(log, index) in logs" :key="index">
                        <div x-text="log" class="py-0.5" :class="{'text-yellow-400': log.includes('WARNING'), 'text-red-400': log.includes('ERROR'), 'text-blue-400': log.includes('==='), 'text-cyan-300': log.includes('Successfully')}"></div>
                    </template>
                </div>
            </div>
        </div>

        <!-- Questions Panel -->
        <div class="bg-white rounded-lg shadow-md p-6">
            <div class="flex justify-between items-center mb-4 flex-wrap gap-2">
                <h2 class="text-xl font-semibold text-gray-800">Saved Questions</h2>
                <div class="flex gap-2">
                    <a 
                        href="/api/questions/export/csv"
                        download="questions.csv"
                        class="px-4 py-2 bg-green-100 text-green-800 rounded-lg hover:bg-green-200 transition-colors flex items-center gap-2"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                        Download CSV
                    </a>
                    <button 
                        @click="loadQuestions()"
                        class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors flex items-center gap-2"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                        Refresh
                    </button>
                </div>
            </div>
            
            <div class="text-sm text-gray-600 mb-4">
                Total: <span x-text="totalQuestions" class="font-semibold"></span> questions
            </div>
            
            <!-- Loading State -->
            <div x-show="loadingQuestions" class="text-center py-8">
                <svg class="animate-spin h-8 w-8 mx-auto text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                </svg>
                <p class="mt-2 text-gray-600">Loading questions...</p>
            </div>
            
            <!-- Empty State -->
            <div x-show="!loadingQuestions && questions.length === 0" class="text-center py-8">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 mx-auto text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p class="mt-2 text-gray-600">No questions saved yet</p>
                <p class="text-sm text-gray-500">Run the agent to start collecting questions</p>
            </div>
            
            <!-- Questions List -->
            <div x-show="!loadingQuestions && questions.length > 0" class="space-y-4">
                <template x-for="(question, qIndex) in questions" :key="question.id">
                    <div class="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors">
                        <div class="flex justify-between items-start mb-2">
                            <span class="text-xs text-gray-500" x-text="'#' + question.id"></span>
                            <span class="text-xs text-gray-500" x-text="formatDate(question.created_at)"></span>
                        </div>
                        
                        <p class="font-medium text-gray-800 mb-3" x-text="question.question_text"></p>
                        
                        <div class="flex gap-2 flex-wrap text-xs text-gray-500 mb-2 items-center">
                            <span x-show="question.lesson_name">Lesson: <span x-text="question.lesson_name"></span></span>
                            <a x-show="question.lesson_url" 
                               :href="question.lesson_url" 
                               target="_blank" 
                               rel="noopener noreferrer"
                               class="text-blue-600 hover:text-blue-800 hover:underline">
                                Watch video →
                            </a>
                            <span x-show="question.user_email" class="text-gray-400">• by <span x-text="question.user_email"></span></span>
                        </div>
                        
                        <div class="space-y-2">
                            <template x-for="(answer, aIndex) in question.answers" :key="aIndex">
                                <div 
                                    :class="answer.is_selected ? 'bg-blue-50 border-blue-300' : 'bg-gray-50 border-gray-200'"
                                    class="border rounded px-3 py-2 text-sm flex items-center gap-2"
                                >
                                    <span 
                                        :class="answer.is_selected ? 'bg-blue-600 text-white' : 'bg-gray-300 text-gray-600'"
                                        class="w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium"
                                        x-text="answer.position + 1"
                                    ></span>
                                    <span x-text="answer.text" :class="answer.is_selected ? 'text-blue-800 font-medium' : 'text-gray-700'"></span>
                                    <span x-show="answer.is_selected" class="ml-auto text-blue-600">
                                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                                        </svg>
                                    </span>
                                </div>
                            </template>
                        </div>
                    </div>
                </template>
            </div>
            
            <!-- Pagination -->
            <div x-show="totalQuestions > 20" class="mt-6 flex justify-center gap-2">
                <button 
                    @click="prevPage()"
                    :disabled="currentPage === 0"
                    class="px-4 py-2 bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    Previous
                </button>
                <span class="px-4 py-2 text-gray-600">
                    Page <span x-text="currentPage + 1"></span>
                </span>
                <button 
                    @click="nextPage()"
                    :disabled="(currentPage + 1) * 20 >= totalQuestions"
                    class="px-4 py-2 bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    Next
                </button>
            </div>
        </div>
    </div>

    <script>
        function dashboard() {
            return {
                mode: 'single',
                sessionId: localStorage.getItem('agent_session_id') || '',
                unixEmail: '',
                unixPassword: '',
                lessonId: '',
                skipVideo: false,
                batchLessonIds: '',
                batchSkipVideo: false,
                agentStatus: { running: false, current_lesson: null, last_run: null, log_count: 0 },
                logs: [],
                questions: [],
                totalQuestions: 0,
                currentPage: 0,
                loadingQuestions: false,
                pollInterval: null,
                wasRunning: false,
                stopping: false,
                
                init() {
                    this.loadQuestions();
                    this.checkStatus();
                    // Poll for status updates
                    this.pollInterval = setInterval(() => this.checkStatus(), 1500);
                },
                
                async startAgent() {
                    if (!this.lessonId || !this.unixEmail || !this.unixPassword || this.agentStatus.running) return;
                    
                    try {
                        const response = await fetch('/api/agent/start', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ 
                                lesson_id: this.lessonId, 
                                skip_video: this.skipVideo,
                                unix_email: this.unixEmail,
                                unix_password: this.unixPassword
                            })
                        });
                        
                        const data = await response.json();
                        if (response.ok) {
                            this.sessionId = data.session_id;
                            localStorage.setItem('agent_session_id', this.sessionId);
                            this.agentStatus.running = true;
                            this.agentStatus.current_lesson = this.lessonId;
                            this.wasRunning = true;
                        } else if (response.status === 503) {
                            alert(data.detail || 'Server is busy. Maximum concurrent agents reached. Try again later.');
                        }
                    } catch (error) {
                        console.error('Failed to start agent:', error);
                    }
                },
                
                async startBatchAgent() {
                    if (!this.batchLessonIds || !this.unixEmail || !this.unixPassword || this.agentStatus.running) return;
                    
                    try {
                        const response = await fetch('/api/agent/batch', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ 
                                lesson_ids: this.batchLessonIds.trim(),
                                skip_video: this.batchSkipVideo,
                                unix_email: this.unixEmail,
                                unix_password: this.unixPassword
                            })
                        });
                        
                        const data = await response.json();
                        if (response.ok) {
                            this.sessionId = data.session_id;
                            localStorage.setItem('agent_session_id', this.sessionId);
                            this.agentStatus.running = true;
                            this.wasRunning = true;
                        } else if (response.status === 503) {
                            alert(data.detail || 'Server is busy. Maximum concurrent agents reached. Try again later.');
                        }
                    } catch (error) {
                        console.error('Failed to start batch agent:', error);
                    }
                },
                
                async stopAgent() {
                    if (!this.agentStatus.running || !this.sessionId || this.stopping) return;
                    
                    this.stopping = true;
                    try {
                        const response = await fetch('/api/agent/stop', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ session_id: this.sessionId })
                        });
                        
                        if (response.ok) {
                            // Wait for status to update
                            setTimeout(() => {
                                this.checkStatus();
                                this.stopping = false;
                            }, 2000);
                        } else {
                            this.stopping = false;
                        }
                    } catch (error) {
                        console.error('Failed to stop agent:', error);
                        this.stopping = false;
                    }
                },
                
                async checkStatus() {
                    try {
                        const url = this.sessionId ? `/api/agent/status?session_id=${this.sessionId}` : '/api/agent/status';
                        const response = await fetch(url);
                        const data = await response.json();
                        
                        if ((data.running || data.log_count > 0) && this.sessionId) {
                            const logsResponse = await fetch(`/api/agent/logs?session_id=${this.sessionId}`);
                            const newLogs = await logsResponse.json();
                            
                            // Always update logs from server (handles restart when logs are cleared)
                            this.logs = newLogs;
                            if (newLogs.length > 0) {
                                this.$nextTick(() => {
                                    const container = this.$refs.logContainer;
                                    if (container) {
                                        container.scrollTop = container.scrollHeight;
                                    }
                                });
                            }
                        }
                        
                        // Refresh questions when agent finishes
                        if (!data.running && this.wasRunning) {
                            this.wasRunning = false;
                            setTimeout(() => this.loadQuestions(), 1000);
                        }
                        
                        this.agentStatus = data;
                    } catch (error) {
                        console.error('Failed to check status:', error);
                    }
                },
                
                async loadQuestions() {
                    this.loadingQuestions = true;
                    try {
                        const response = await fetch(`/api/questions?limit=20&offset=${this.currentPage * 20}`);
                        const data = await response.json();
                        this.questions = data.questions;
                        this.totalQuestions = data.total;
                    } catch (error) {
                        console.error('Failed to load questions:', error);
                    } finally {
                        this.loadingQuestions = false;
                    }
                },
                
                prevPage() {
                    if (this.currentPage > 0) {
                        this.currentPage--;
                        this.loadQuestions();
                    }
                },
                
                nextPage() {
                    if ((this.currentPage + 1) * 20 < this.totalQuestions) {
                        this.currentPage++;
                        this.loadQuestions();
                    }
                },
                
                formatDate(isoString) {
                    const date = new Date(isoString);
                    return date.toLocaleString();
                }
            };
        }
    </script>
</body>
</html>
    """


@app.post("/api/agent/start")
async def start_agent(request: LessonRequest):
    """Start the agent - creates new session for this user."""
    if not request.unix_email or not request.unix_password:
        raise HTTPException(status_code=400, detail="UniX email and password are required")
    
    session_id = _create_session(mode="single")
    
    thread = threading.Thread(
        target=_run_agent_impl,
        args=(session_id, request.lesson_id, request.skip_video, request.unix_email, request.unix_password)
    )
    thread.daemon = True
    thread.start()
    
    return {"message": "Agent started", "lesson_id": request.lesson_id, "session_id": session_id}


@app.post("/api/agent/batch")
async def start_batch_agent(request: BatchRequest):
    """Start batch agent - processes comma-separated lesson IDs sequentially."""
    if not request.unix_email or not request.unix_password:
        raise HTTPException(status_code=400, detail="UniX email and password are required")
    if not request.lesson_ids or not any(x.strip() for x in request.lesson_ids.split(",")):
        raise HTTPException(status_code=400, detail="At least one lesson ID is required (comma-separated)")
    
    session_id = _create_session(mode="batch")
    
    thread = threading.Thread(
        target=_run_batch_agent_impl,
        args=(session_id, request.lesson_ids, request.skip_video, request.unix_email, request.unix_password)
    )
    thread.daemon = True
    thread.start()
    
    ids = [x.strip() for x in request.lesson_ids.split(",") if x.strip()]
    return {
        "message": "Batch agent started",
        "session_id": session_id,
        "lesson_ids": ids,
        "count": len(ids)
    }


@app.post("/api/agent/stop")
async def stop_agent(request: StopRequest):
    """Stop the agent for this session."""
    session_id = request.session_id
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    
    with sessions_lock:
        session = agent_sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if not session.get("running"):
            return {"message": "Agent stopped"}
        
        process = session.get("process")
        if process:
            try:
                process.terminate()
                session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ⏹️ Stopping agent...")
                time.sleep(2)
                if process.poll() is None:
                    process.kill()
                    session["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Force killed agent")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        session["running"] = False
        session["process"] = None
    
    return {"message": "Agent stopped"}


@app.get("/api/agent/status")
async def get_agent_status(session_id: str = Query("", alias="session_id")) -> AgentStatus:
    """Get agent status for a session."""
    if not session_id:
        return AgentStatus(running=False, current_lesson=None, last_run=None, log_count=0, session_id=None)
    
    session = agent_sessions.get(session_id)
    if not session:
        return AgentStatus(running=False, current_lesson=None, last_run=None, log_count=0, session_id=session_id)
    
    return AgentStatus(
        running=session.get("running", False),
        current_lesson=session.get("current_lesson"),
        last_run=session.get("last_run"),
        log_count=len(session.get("logs", [])),
        session_id=session_id
    )


@app.get("/api/agent/logs")
async def get_agent_logs(session_id: str = Query("", alias="session_id")) -> List[str]:
    """Get agent logs for a session."""
    if not session_id:
        return []
    session = agent_sessions.get(session_id)
    if not session:
        return []
    return session.get("logs", [])


@app.get("/api/questions")
async def get_questions(limit: int = 20, offset: int = 0):
    """Get saved questions with pagination. Shows all questions (shared demo - no user filter)."""
    db = get_db()
    if not db:
        return {"questions": [], "total": 0}
    
    questions = db.get_all_questions(limit=limit, offset=offset)
    total = db.get_all_question_count()
    
    return {"questions": questions, "total": total}


@app.get("/api/questions/count")
async def get_question_count():
    """Get total number of questions."""
    db = get_db()
    if not db:
        return {"count": 0}
    
    count = db.get_all_question_count()
    return {"count": count}


@app.get("/api/questions/export/csv")
async def export_questions_csv():
    """Export all questions to CSV (as stored in DB)."""
    db = get_db()
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")
    
    questions = db.get_all_questions(limit=None, offset=0)
    
    # Find max answers count
    max_answers = max((len(q.get("answers", [])) for q in questions), default=0)
    
    def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        # Header: id, question_text, lesson_name, lesson_url, created_at, user_email, answer_1..N, selected_answer
        header = ["id", "question_text", "lesson_name", "lesson_url", "created_at", "user_email"]
        header += [f"answer_{i+1}" for i in range(max_answers)]
        header.append("selected_answer")
        writer.writerow(header)
        
        for q in questions:
            answers = q.get("answers", [])
            selected = next((a["text"] for a in answers if a.get("is_selected")), "")
            row = [
                q.get("id"),
                q.get("question_text", ""),
                q.get("lesson_name", ""),
                q.get("lesson_url", ""),
                q.get("created_at", ""),
                q.get("user_email", ""),
            ]
            for i in range(max_answers):
                row.append(answers[i]["text"] if i < len(answers) else "")
            row.append(selected)
            writer.writerow(row)
        
        buffer.seek(0)
        return buffer.getvalue()
    
    # Add BOM for Excel UTF-8
    content = "\ufeff" + generate()
    
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=questions.csv"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
