"""
FastAPI Web Interface for UniX Agent

Provides a web UI to:
- View stored questions and answers
- Start the agent to process lessons
- Monitor agent status
"""

import os
import subprocess
import threading
import time
import signal
from datetime import datetime
from typing import Optional, List
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db_models import DatabaseManager

load_dotenv()

app = FastAPI(title="UniX Agent Dashboard", version="1.0.0")

# Global state for agent
agent_state = {
    "running": False,
    "current_lesson": None,
    "mode": "single",  # "single" or "batch"
    "logs": [],
    "last_run": None,
    "process": None  # Store the subprocess reference
}

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


class BatchRequest(BaseModel):
    start_id: int
    end_id: Optional[int] = None
    max_lessons: int = 50
    skip_video: bool = False


class AgentStatus(BaseModel):
    running: bool
    current_lesson: Optional[str]
    last_run: Optional[str]
    log_count: int


def run_agent(lesson_id: str, skip_video: bool = True):
    """Run the agent in a background thread."""
    global agent_state
    
    agent_state["running"] = True
    agent_state["current_lesson"] = lesson_id
    agent_state["mode"] = "single"
    agent_state["logs"] = []
    agent_state["process"] = None
    
    try:
        lesson_url = f"https://uni-x.almv.kz/platform/lessons/{lesson_id}"
        cmd = ["python3", "unix_agent.py", "--lesson", lesson_url]
        if skip_video:
            cmd.append("--skip-video")
        
        agent_state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Starting agent for lesson {lesson_id}...")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        agent_state["process"] = process
        
        for line in iter(process.stdout.readline, ''):
            if line:
                agent_state["logs"].append(line.strip())
                # Keep only last 200 log lines
                if len(agent_state["logs"]) > 200:
                    agent_state["logs"] = agent_state["logs"][-200:]
            # Check if process was killed
            if process.poll() is not None:
                break
        
        process.wait()
        exit_code = process.returncode
        if exit_code == -9 or exit_code == -15:
            agent_state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ⛔ Agent stopped by user")
        else:
            agent_state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Agent finished with exit code {exit_code}")
        
    except Exception as e:
        agent_state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {str(e)}")
    finally:
        agent_state["running"] = False
        agent_state["process"] = None
        agent_state["last_run"] = datetime.now().isoformat()


def run_batch_agent(start_id: int, end_id: Optional[int], max_lessons: int, skip_video: bool):
    """Run the agent in batch mode to process multiple lessons."""
    global agent_state
    
    agent_state["running"] = True
    agent_state["current_lesson"] = f"Batch: {start_id} → {end_id or (start_id + max_lessons)}"
    agent_state["mode"] = "batch"
    agent_state["logs"] = []
    agent_state["process"] = None
    
    try:
        cmd = ["python3", "unix_agent.py", "--batch", "--start-id", str(start_id), "--max-lessons", str(max_lessons)]
        if end_id:
            cmd.extend(["--end-id", str(end_id)])
        if skip_video:
            cmd.append("--skip-video")
        
        agent_state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Starting BATCH mode from lesson {start_id}...")
        agent_state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Max lessons: {max_lessons}, Skip video: {skip_video}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        agent_state["process"] = process
        
        for line in iter(process.stdout.readline, ''):
            if line:
                # Parse the line to update current lesson
                line_stripped = line.strip()
                if "Processing lesson" in line_stripped:
                    try:
                        # Extract lesson ID from log
                        import re
                        match = re.search(r'Processing lesson (\d+)', line_stripped)
                        if match:
                            agent_state["current_lesson"] = f"Lesson {match.group(1)}"
                    except:
                        pass
                
                agent_state["logs"].append(line_stripped)
                # Keep only last 500 log lines for batch mode
                if len(agent_state["logs"]) > 500:
                    agent_state["logs"] = agent_state["logs"][-500:]
            
            # Check if process was killed
            if process.poll() is not None:
                break
        
        process.wait()
        exit_code = process.returncode
        if exit_code == -9 or exit_code == -15:
            agent_state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ⛔ Batch stopped by user")
        else:
            agent_state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Batch finished with exit code {exit_code}")
        
    except Exception as e:
        agent_state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Error: {str(e)}")
    finally:
        agent_state["running"] = False
        agent_state["process"] = None
        agent_state["last_run"] = datetime.now().isoformat()


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
                        placeholder="e.g., 9843"
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
                    :disabled="agentStatus.running || !lessonId"
                    class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                >
                    Start Agent
                </button>
            </div>
            
            <!-- Batch Mode -->
            <div x-show="mode === 'batch'" class="space-y-4">
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Start Lesson ID *</label>
                        <input 
                            type="number" 
                            x-model="batchStartId" 
                            placeholder="e.g., 9840"
                            class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            :disabled="agentStatus.running"
                        >
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">End Lesson ID (optional)</label>
                        <input 
                            type="number" 
                            x-model="batchEndId" 
                            placeholder="Auto-detect end"
                            class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            :disabled="agentStatus.running"
                        >
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Max Lessons</label>
                        <input 
                            type="number" 
                            x-model="maxLessons" 
                            placeholder="50"
                            class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            :disabled="agentStatus.running"
                        >
                    </div>
                </div>
                
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <input type="checkbox" x-model="batchSkipVideo" id="batchSkipVideo" class="rounded">
                        <label for="batchSkipVideo" class="text-sm text-gray-700">Skip Videos (test only)</label>
                    </div>
                    
                    <button 
                        @click="startBatchAgent()"
                        :disabled="agentStatus.running || !batchStartId"
                        class="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clip-rule="evenodd" />
                        </svg>
                        Start Batch
                    </button>
                </div>
                
                <div class="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
                    <strong>Batch Mode:</strong> The agent will automatically process all lessons starting from the Start ID. 
                    It will watch videos, complete tests, and move to the next lesson (ID + 1) until it reaches the End ID 
                    or the maximum number of lessons.
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
            <div class="flex justify-between items-center mb-4">
                <h2 class="text-xl font-semibold text-gray-800">Saved Questions</h2>
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
                        
                        <div x-show="question.lesson_name" class="text-xs text-gray-500 mb-2">
                            Lesson: <span x-text="question.lesson_name"></span>
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
                lessonId: '',
                skipVideo: true,
                batchStartId: '',
                batchEndId: '',
                maxLessons: 50,
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
                    if (!this.lessonId || this.agentStatus.running) return;
                    
                    try {
                        const response = await fetch('/api/agent/start', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ lesson_id: this.lessonId, skip_video: this.skipVideo })
                        });
                        
                        if (response.ok) {
                            this.agentStatus.running = true;
                            this.agentStatus.current_lesson = this.lessonId;
                            this.wasRunning = true;
                        }
                    } catch (error) {
                        console.error('Failed to start agent:', error);
                    }
                },
                
                async startBatchAgent() {
                    if (!this.batchStartId || this.agentStatus.running) return;
                    
                    try {
                        const response = await fetch('/api/agent/batch', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ 
                                start_id: parseInt(this.batchStartId), 
                                end_id: this.batchEndId ? parseInt(this.batchEndId) : null,
                                max_lessons: parseInt(this.maxLessons) || 50,
                                skip_video: this.batchSkipVideo 
                            })
                        });
                        
                        if (response.ok) {
                            this.agentStatus.running = true;
                            this.wasRunning = true;
                        }
                    } catch (error) {
                        console.error('Failed to start batch agent:', error);
                    }
                },
                
                async stopAgent() {
                    if (!this.agentStatus.running || this.stopping) return;
                    
                    this.stopping = true;
                    try {
                        const response = await fetch('/api/agent/stop', {
                            method: 'POST'
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
                        const response = await fetch('/api/agent/status');
                        const data = await response.json();
                        
                        // Fetch logs if running or has logs
                        if (data.running || data.log_count > 0) {
                            const logsResponse = await fetch('/api/agent/logs');
                            const newLogs = await logsResponse.json();
                            
                            // Auto-scroll if new logs
                            if (newLogs.length > this.logs.length) {
                                this.logs = newLogs;
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
async def start_agent(request: LessonRequest, background_tasks: BackgroundTasks):
    """Start the agent to process a lesson."""
    if agent_state["running"]:
        raise HTTPException(status_code=400, detail="Agent is already running")
    
    # Start agent in background
    thread = threading.Thread(
        target=run_agent, 
        args=(request.lesson_id, request.skip_video)
    )
    thread.daemon = True
    thread.start()
    
    return {"message": "Agent started", "lesson_id": request.lesson_id}


@app.post("/api/agent/batch")
async def start_batch_agent(request: BatchRequest):
    """Start the agent in batch mode to process multiple lessons."""
    if agent_state["running"]:
        raise HTTPException(status_code=400, detail="Agent is already running")
    
    # Start agent in background
    thread = threading.Thread(
        target=run_batch_agent, 
        args=(request.start_id, request.end_id, request.max_lessons, request.skip_video)
    )
    thread.daemon = True
    thread.start()
    
    return {
        "message": "Batch agent started", 
        "start_id": request.start_id,
        "end_id": request.end_id,
        "max_lessons": request.max_lessons
    }


@app.post("/api/agent/stop")
async def stop_agent():
    """Stop the running agent."""
    if not agent_state["running"]:
        raise HTTPException(status_code=400, detail="Agent is not running")
    
    process = agent_state.get("process")
    if process:
        try:
            # Try graceful termination first
            process.terminate()
            agent_state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] ⏹️ Stopping agent...")
            
            # Wait a bit for graceful shutdown
            time.sleep(2)
            
            # Force kill if still running
            if process.poll() is None:
                process.kill()
                agent_state["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] Force killed agent")
            
            return {"message": "Agent stopped"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to stop agent: {str(e)}")
    else:
        agent_state["running"] = False
        return {"message": "Agent state reset"}


@app.get("/api/agent/status")
async def get_agent_status() -> AgentStatus:
    """Get current agent status."""
    return AgentStatus(
        running=agent_state["running"],
        current_lesson=agent_state["current_lesson"],
        last_run=agent_state["last_run"],
        log_count=len(agent_state["logs"])
    )


@app.get("/api/agent/logs")
async def get_agent_logs() -> List[str]:
    """Get agent logs."""
    return agent_state["logs"]


@app.get("/api/questions")
async def get_questions(limit: int = 20, offset: int = 0):
    """Get saved questions with pagination."""
    db = get_db()
    if not db:
        return {"questions": [], "total": 0}
    
    user_email = os.getenv("UNIX_EMAIL")
    if not user_email:
        return {"questions": [], "total": 0}
    
    questions = db.get_user_questions(user_email, limit=limit, offset=offset)
    total = db.get_question_count(user_email)
    
    return {"questions": questions, "total": total}


@app.get("/api/questions/count")
async def get_question_count():
    """Get total number of questions."""
    db = get_db()
    if not db:
        return {"count": 0}
    
    user_email = os.getenv("UNIX_EMAIL")
    if not user_email:
        return {"count": 0}
    
    count = db.get_question_count(user_email)
    return {"count": count}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
