// NeuraQuiz Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Auto-hide only ephemeral alerts (those we create programmatically or inside #alert-container)
    const alerts = document.querySelectorAll('#alert-container .alert, .alert[data-autohide="true"]');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });

    // Add fade-in animation to cards
    const cards = document.querySelectorAll('.quiz-card, .stats-card, .feature-card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(30px)';
        
        setTimeout(() => {
            card.style.transition = 'all 0.6s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });

    // Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // Add loading states to forms' submit events.
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function(event) {
            if (form.checkValidity()) {
                const submitBtn = form.querySelector('button[type="submit"]');
                if (submitBtn) {
                    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Loading...';
                    submitBtn.disabled = true;
                }
            }
        });
    });

    // Form validation enhancement
    const forms = document.querySelectorAll('.needs-validation');
    forms.forEach(form => {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });

    // Quiz timer functionality
    if (typeof window.quizTimer !== 'undefined') {
        window.quizTimer.init();
    }

    // AI generation functionality
    if (typeof window.aiGenerator !== 'undefined') {
        window.aiGenerator.init();
    }

    // Exit quiz button (if present)
    const exitBtn = document.getElementById('exit-quiz-btn');
    if (exitBtn) {
        exitBtn.addEventListener('click', (e) => {
            e.preventDefault();
            const exitModal = new bootstrap.Modal(document.getElementById('exitModal'));
            exitModal.show();
        });
    }
});

// Quiz Timer Class
class QuizTimer {
    constructor() {
        this.timeLeft = 0;
        this.timerElement = null;
        this.progressElement = null;
        this.interval = null;
    }

    init() {
        this.timerElement = document.getElementById('quiz-timer');
        this.progressElement = document.getElementById('timer-progress');
        
        if (this.timerElement && this.progressElement) {
            this.timeLeft = parseInt(this.timerElement.dataset.timeLeft) || 0;
            this.totalTime = parseInt(this.timerElement.dataset.totalTime) || 0;
            this.start();
        }
    }

    start() {
        this.updateDisplay();
        this.interval = setInterval(() => {
            this.timeLeft--;
            this.updateDisplay();
            
            if (this.timeLeft <= 0) {
                this.stop();
                this.handleTimeUp();
            }
        }, 1000);
    }

    stop() {
        if (this.interval) {
            clearInterval(this.interval);
            this.interval = null;
        }
    }

    updateDisplay() {
        const minutes = Math.floor(this.timeLeft / 60);
        const seconds = this.timeLeft % 60;
        
        this.timerElement.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        
        const progress = ((this.totalTime - this.timeLeft) / this.totalTime) * 100;
        this.progressElement.style.width = `${progress}%`;
        
        // Change color based on time remaining
        if (this.timeLeft <= 60) {
            this.timerElement.classList.add('text-danger');
            this.progressElement.classList.add('bg-danger');
        } else if (this.timeLeft <= 300) {
            this.timerElement.classList.add('text-warning');
            this.progressElement.classList.add('bg-warning');
        }
    }

    handleTimeUp() {
        // Auto-submit quiz when time is up
        const submitButton = document.getElementById('submit-quiz');
        if (submitButton) {
            submitButton.click();
        }
    }
}

// AI Generator Class
class AIGenerator {
    constructor() {
        this.generateButton = null;
        this.loadingElement = null;
        this.currentAbortController = null;
        this.isGenerating = false;
        this._state = 'idle';
        this._retryInterval = null;
        this._statusPoll = null;
        this.modalElement = null;
        this.modalInstance = null;
    }

    init() {
        this.generateButton = document.getElementById('generate-ai-questions');
        this.loadingElement = document.getElementById('ai-loading');
        this.modalElement = document.getElementById('aiModal');
        
        if (this.generateButton) {
            const aiEnabledAttr = this.generateButton.dataset.aiEnabled;
            const aiEnabled = (aiEnabledAttr === 'true' || aiEnabledAttr === true);

            if (!aiEnabled) {
                this.generateButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.showError('AI service is not configured. Please set GEMINI_API_KEY and restart the server.');
                });
            } else {
                this.generateButton.addEventListener('click', this.handleGenerate.bind(this));
                
                // Handle modal close/cancel events
                if (this.modalElement) {
                    // Bootstrap modal hide event
                    this.modalElement.addEventListener('hide.bs.modal', (e) => {
                        this.handleModalClose();
                    });
                    
                    // Cancel button click
                    const cancelBtn = this.modalElement.querySelector('button[data-bs-dismiss="modal"]');
                    if (cancelBtn) {
                        cancelBtn.addEventListener('click', (e) => {
                            this.handleModalClose();
                        });
                    }
                    
                    // X button click
                    const closeBtn = this.modalElement.querySelector('.btn-close');
                    if (closeBtn) {
                        closeBtn.addEventListener('click', (e) => {
                            this.handleModalClose();
                        });
                    }
                }
            }
        }
    }

    async handleModalClose() {
        // Send cancellation request to backend
        if (this.isGenerating) {
            const quizId = this.generateButton?.dataset?.quizId;
            if (quizId) {
                try {
                    await fetch(`/cancel-ai-generation/${quizId}/`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCSRFToken()
                        },
                        credentials: 'same-origin'
                    });
                    console.log('Cancellation request sent to backend');
                } catch (err) {
                    console.error('Error sending cancellation request:', err);
                }
            }
        }
        
        // Cancel any in-flight request
        if (this.isGenerating && this.currentAbortController) {
            try {
                this.currentAbortController.abort();
            } catch (err) {
                console.error('Error aborting request:', err);
            }
            this.isGenerating = false;
            this._state = 'cancelled';
        }
        
        // Clear any scheduled retry
        if (this._retryInterval) {
            clearInterval(this._retryInterval);
            this._retryInterval = null;
        }
        
        // Clear any status poll
        if (this._statusPoll) {
            clearInterval(this._statusPoll);
            this._statusPoll = null;
        }
        
        // Reset modal to initial state
        this.resetModalState();
    }

    resetModalState() {
        // Reset loading element
        if (this.loadingElement) {
            this.loadingElement.style.display = 'none';
            this.loadingElement.innerHTML = '';
            delete this.loadingElement.dataset.persist;
        }
        
        // Reset button
        if (this.generateButton) {
            this.generateButton.disabled = false;
            if (this.generateButton.dataset.origHtml) {
                this.generateButton.innerHTML = this.generateButton.dataset.origHtml;
                delete this.generateButton.dataset.origHtml;
            } else {
                this.generateButton.innerHTML = '<i class="fas fa-robot me-2"></i>Generate Questions';
            }
        }
        
        // Reset state
        this._state = 'idle';
        this.isGenerating = false;
        this.currentAbortController = null;
    }

    handleRateLimitRetry(retrySeconds) {
        this._state = 'retrying';
        let wait = 5;
        try {
            if (retrySeconds && Number.isFinite(Number(retrySeconds)) && Number(retrySeconds) > 0) {
                wait = Math.max(1, parseInt(retrySeconds, 10));
            }
        } catch (e) {}

        this.showAlert(`AI generation is in progress. Retrying in ${wait} seconds...`, 'info');

        if (!this.generateButton.dataset.origHtml) {
            this.generateButton.dataset.origHtml = this.generateButton.innerHTML;
        }

        this.generateButton.disabled = true;
        let remaining = wait;
        this.generateButton.innerHTML = `Retrying in ${remaining}s...`;

        if (this._retryInterval) {
            clearInterval(this._retryInterval);
            this._retryInterval = null;
        }

        this._retryInterval = setInterval(() => {
            remaining -= 1;
            if (remaining <= 0) {
                clearInterval(this._retryInterval);
                this._retryInterval = null;
                if (this.generateButton.dataset.origHtml) {
                    this.generateButton.innerHTML = this.generateButton.dataset.origHtml;
                    delete this.generateButton.dataset.origHtml;
                } else {
                    this.generateButton.innerHTML = '<i class="fas fa-robot me-2"></i>Generate Questions';
                }
                this.generateButton.disabled = false;
                try {
                    this.handleGenerate(null);
                } catch (e) {
                    console.error('Retry generate failed', e);
                }
            } else {
                this.generateButton.innerHTML = `Retrying in ${remaining}s...`;
            }
        }, 1000);
    }

    async handleGenerate(event) {
        if (event && event.preventDefault) event.preventDefault();

        try {
            this._state = 'generating';
            this.showLoading();
        } catch (e) {
            console.error('showLoading failed', e);
        }

        const quizId = this.generateButton?.dataset?.quizId;
        const topic = (document.getElementById('ai-topic') && document.getElementById('ai-topic').value) || '';
        const numQuestions = parseInt(document.getElementById('ai-num-questions')?.value, 10) || 10;
        // Use quiz difficulty from backend instead of user selection
        const quizDifficulty = this.generateButton?.dataset?.quizDifficulty;
        const difficulty = quizDifficulty || 'medium';

        try {
            this.currentAbortController = new AbortController();
            this.isGenerating = true;
        } catch (e) {
            this.currentAbortController = null;
            this.isGenerating = false;
        }

        let response = null;
        let data = null;
        try {
            response = await fetch(`/generate-ai-questions/${quizId}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                credentials: 'same-origin',
                signal: this.currentAbortController ? this.currentAbortController.signal : undefined,
                body: JSON.stringify({
                    topic: topic,
                    num_questions: parseInt(numQuestions),
                    difficulty: difficulty,
                    additional_instructions: (document.getElementById('ai-instructions') && document.getElementById('ai-instructions').value) || ''
                })
            });

            try {
                data = await response.json();
                
                // Check if generation was cancelled
                if (data && data.cancelled) {
                    this._state = 'cancelled';
                    console.log('Generation was cancelled on the backend');
                    this.isGenerating = false;
                    this.currentAbortController = null;
                    this.hideLoading();
                    return;
                }
                
                if (response.status === 202 || (data && data.pending)) {
                    this.handlePendingGeneration(quizId);
                    return;
                }
            } catch (err) {
                if (!response.ok) {
                    if (response.status === 202) {
                        this.handlePendingGeneration(quizId);
                        return;
                    }
                    if (response.status === 429) {
                        const retryHeader = response.headers.get('Retry-After');
                        const retrySeconds = retryHeader ? parseInt(retryHeader, 10) : null;
                        this.handleRateLimitRetry(retrySeconds || (data && data.retry_seconds));
                        return;
                    }
                    this.showError(`AI generation failed (status ${response.status}).`);
                    this.isGenerating = false;
                    this.currentAbortController = null;
                    this.hideLoading();
                    return;
                }
                this.showError('Unexpected response from server.');
                this.isGenerating = false;
                this.currentAbortController = null;
                this.hideLoading();
                return;
            }

            if (!response.ok) {
                if (response.status === 202 || (data && data.pending)) {
                    this.handlePendingGeneration(quizId);
                    return;
                }
                if (response.status === 429) {
                    const retryHeader = response.headers.get('Retry-After');
                    const retrySeconds = retryHeader ? parseInt(retryHeader, 10) : (data && data.retry_seconds ? parseInt(data.retry_seconds, 10) : null);
                    this.handleRateLimitRetry(retrySeconds);
                    return;
                }

                this._state = 'error';
                this.showError(data.error || data.message || `AI service error (${response.status}).`);
                this.isGenerating = false;
                this.currentAbortController = null;
                this.hideLoading();
                return;
            }

            if (data && data.success) {
                // Success: update UI and questions
                this.updateQuestionsList(data.questions || []);
                try {
                    await this.refreshQuestionsList(quizId);
                    await this.refreshQuizStats(quizId);
                } catch (e) {
                    console.error(e);
                }
                this.showSuccess('Questions generated successfully.');
                this._state = 'completed';
                this.isGenerating = false;
                this.currentAbortController = null;
                this.resetButton();
                return;
            } else {
                this._state = 'error';
                this.showError((data && (data.error || data.message)) || 'Failed to generate questions');
                this.isGenerating = false;
                this.currentAbortController = null;
                this.hideLoading();
                return;
            }
        } catch (error) {
            if (error && error.name === 'AbortError') {
                this._state = 'cancelled';
                // Don't show error message on intentional cancel
                console.log('AI generation cancelled by user');
            } else {
                console.error('AI generate error', error);
                this._state = 'error';
                this.showError('Network error. Please try again.');
            }
            this.isGenerating = false;
            this.currentAbortController = null;
            this.hideLoading();
            return;
        }
    }

    getCSRFToken() {
        const tokenInput = document.querySelector('#ai-generation-form [name=csrfmiddlewaretoken]');
        if (tokenInput) return tokenInput.value;
        const match = document.cookie.match(/csrftoken=([^;]+)/);
        return match ? match[1] : '';
    }

    showLoading() {
        if (!this.generateButton) return;

        this._state = this._state || 'generating';

        if (!this.generateButton.dataset.origHtml) {
            this.generateButton.dataset.origHtml = this.generateButton.innerHTML;
        }

        this.generateButton.disabled = true;
        this.generateButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Generating...';

        if (this.loadingElement) {
            this.loadingElement.style.display = 'block';
            this.loadingElement.innerHTML = `
                <div class="d-flex align-items-center justify-content-center gap-3 p-4">
                    <div class="spinner-border text-primary" style="width: 3rem; height: 3rem;" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <div class="h5 mb-0 text-primary">Generating questions this may take a moment...</div>
                </div>`;
        }
    }

    hideLoading() {
        if (!this.generateButton) return;
        if (this.loadingElement && this.loadingElement.dataset && this.loadingElement.dataset.persist === 'true') {
            return;
        }
        const allowedToHide = ['error', 'cancelled', 'idle'];
        if (!allowedToHide.includes(this._state)) {
            return;
        }

        this.generateButton.disabled = false;
        if (this.generateButton.dataset.origHtml) {
            this.generateButton.innerHTML = this.generateButton.dataset.origHtml;
            delete this.generateButton.dataset.origHtml;
        } else {
            this.generateButton.innerHTML = '<i class="fas fa-robot me-2"></i>Generate Questions';
        }

        if (this.loadingElement) {
            this.loadingElement.style.display = 'none';
            this.loadingElement.innerHTML = '';
        }

        this._state = 'idle';
    }

    resetButton() {
        if (!this.generateButton) return;
        
        this.generateButton.disabled = false;
        if (this.generateButton.dataset.origHtml) {
            this.generateButton.innerHTML = this.generateButton.dataset.origHtml;
            delete this.generateButton.dataset.origHtml;
        } else {
            this.generateButton.innerHTML = '<i class="fas fa-robot me-2"></i>Generate Questions';
        }
    }

    async refreshQuestionsList(quizId) {
        try {
            const url = `/edit-quiz/${quizId}/`;
            const resp = await fetch(url, { credentials: 'same-origin' });
            if (!resp.ok) return;
            const html = await resp.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const newList = doc.getElementById('questions-list');
            const currentList = document.getElementById('questions-list');
            if (newList && currentList) {
                currentList.innerHTML = newList.innerHTML;
            }
        } catch (e) {
            console.error('Failed to refresh questions list', e);
        }
    }

    async refreshQuizStats(quizId) {
        try {
            const resp = await fetch(`/quiz-stats/${quizId}/`, { credentials: 'same-origin' });
            if (!resp.ok) return;
            const data = await resp.json();
            
            // Update stats cards with data attributes
            const questionsCard = document.querySelector('[data-stat="questions-count"]');
            if (questionsCard) {
                questionsCard.textContent = data.questions_count || 0;
            }
            
            const aiGeneratedCard = document.querySelector('[data-stat="ai-generated-count"]');
            if (aiGeneratedCard) {
                aiGeneratedCard.textContent = data.ai_generated_count || 0;
            }
        } catch (e) {
            console.error('Failed to refresh quiz stats', e);
        }
    }

    showSuccess(message) {
        this.showAlert(message, 'success');
        if (this.loadingElement) {
            this.loadingElement.innerHTML = `
                <div class="text-center p-4">
                    <div class="mb-3">
                        <i class="fas fa-check-circle text-success" style="font-size: 3rem;"></i>
                    </div>
                    <h5 class="text-success mb-0">Questions generated successfully.</h5>
                </div>`;
            this.loadingElement.style.display = 'block';
            this.loadingElement.dataset.persist = 'true';
        }
    }

    showError(message) {
        this.showAlert(message, 'danger');
    }

    async handlePendingGeneration(quizId) {
        this._state = 'pending';
        
        try {
            this.showLoading();
        } catch (e) {}

        if (this.loadingElement) {
            this.loadingElement.innerHTML = `
                <div class="d-flex align-items-center justify-content-center gap-3 p-4">
                    <div class="spinner-border text-primary" style="width: 3rem; height: 3rem;" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <div class="h5 mb-0 text-muted">
                        AI generation is running on the server. Please wait...
                    </div>
                </div>`;
            this.loadingElement.style.display = 'block';
            delete this.loadingElement.dataset.persist;
        }

        const maxPolls = 60;
        const intervalMs = 3000;
        let polls = 0;

        if (this._statusPoll) {
            clearInterval(this._statusPoll);
            this._statusPoll = null;
        }

        this._statusPoll = setInterval(async () => {
            polls += 1;
            try {
                const resp = await fetch(`/generate-ai-status/${quizId}/`, { credentials: 'same-origin' });
                if (!resp.ok) {
                    if (resp.status === 403) {
                        this.showError('Permission denied checking AI generation status.');
                        clearInterval(this._statusPoll);
                        this._statusPoll = null;
                        this.hideLoading();
                        return;
                    }
                } else {
                    const js = await resp.json().catch(() => null);
                    if (js && js.in_progress === false) {
                        clearInterval(this._statusPoll);
                        this._statusPoll = null;
                        try {
                            await this.refreshQuestionsList(quizId);
                            await this.refreshQuizStats(quizId);
                        } catch (e) {
                            console.error(e);
                        }
                        this._state = 'completed';
                        this.showSuccess('Questions generated successfully.');
                        this.resetButton();
                        return;
                    }
                }
            } catch (err) {
                console.error('Error polling generation status', err);
            }

            if (polls >= maxPolls) {
                clearInterval(this._statusPoll);
                this._statusPoll = null;
                this._state = 'error';
                this.showError('AI generation is taking longer than expected. Please check server logs or try again later.');
                this.hideLoading();
            }
        }, intervalMs);
    }

    showAlert(message, type) {
        const alertContainer = document.getElementById('alert-container') || document.body;
        const alert = document.createElement('div');
        alert.className = `alert alert-${type} alert-dismissible fade show`;
        alert.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        alert.setAttribute('data-autohide', 'true');
        
        alertContainer.insertBefore(alert, alertContainer.firstChild);
        
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    }

    updateQuestionsList(questions) {
        const questionsList = document.getElementById('questions-list');
        if (questionsList && questions.length > 0) {
            const baseIndex = questionsList.querySelectorAll('.question-item').length;
            questions.forEach((question, idx) => {
                const qNumber = baseIndex + idx + 1;
                const questionElement = this.createQuestionElement(question, qNumber);
                questionsList.appendChild(questionElement);
            });
        }
    }

    createQuestionElement(question, questionNumber) {
        const div = document.createElement('div');
        div.className = 'question-item card mb-3';
        const aiBadge = (question.ai_generated || question.aiGenerated) ? `<span class="badge bg-primary"><i class="fas fa-robot me-1"></i>AI</span>` : '';
        div.innerHTML = `
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1">
                        <h6 class="card-title">Question ${questionNumber}</h6>
                        <p class="card-text">${question.text}</p>
                    </div>
                    <div class="d-flex gap-2 align-items-center flex-nowrap" style="white-space: nowrap;">
                        <span class="badge bg-primary">${(question.type || question.question_type || '').toString().replace(/_/g,' ').replace(/\b\w/g, c => c.toUpperCase())}</span>
                        ${aiBadge}
                    </div>
                </div>
                <small class="text-muted">Difficulty: ${question.difficulty_score}/5.0</small>
            </div>
        `;
        return div;
    }
}

// Quiz Taking Functionality
class QuizTaker {
    constructor() {
        this.currentQuestion = 0;
        this.answers = {};
        this.questions = [];
        this.statuses = [];
    }

    init() {
        this.questions = Array.from(document.querySelectorAll('.question-container'));
        this.statuses = this.questions.map(() => 'not_viewed');
        this.setupEventListeners();
        this.showQuestion(0);
    }

    setupEventListeners() {
        document.getElementById('next-question')?.addEventListener('click', () => this.nextQuestion());
        document.getElementById('prev-question')?.addEventListener('click', () => this.prevQuestion());
        document.getElementById('submit-answer')?.addEventListener('click', () => this.submitAnswer());
        
        const submitBtn = document.getElementById('submit-quiz');
        if (submitBtn) {
            const opensModal = submitBtn.dataset.opensModal === 'true' || submitBtn.getAttribute('data-opens-modal') === 'true';
            if (!opensModal) {
                submitBtn.addEventListener('click', () => this.submitQuiz());
            }
        }

        document.querySelectorAll('.question-indicator').forEach((btn) => {
            btn.removeAttribute('onclick');
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const idx = parseInt(btn.dataset.questionIndex ?? Array.from(document.querySelectorAll('.question-indicator')).indexOf(btn));
                if (!Number.isNaN(idx)) this.goToQuestion(idx);
            });
        });

        this.questions.forEach((questionEl, index) => {
            const inputs = questionEl.querySelectorAll('input, textarea');
            inputs.forEach(inp => {
                inp.addEventListener('change', () => {
                    const answerData = this.collectAnswer(questionEl);
                    const qid = questionEl.dataset.questionId;
                    this.answers[qid] = answerData;
                    this.statuses[index] = 'answered';
                    this.updateQuestionIndicators();
                    this.submitAnswerToServer(answerData);
                });
            });
        });
    }

    showQuestion(index) {
        this.questions.forEach((question, i) => {
            question.style.display = i === index ? 'block' : 'none';
        });
        if (this.statuses[index] === 'not_viewed') {
            this.statuses[index] = 'viewed_unanswered';
        }

        this.currentQuestion = index;
        this.updateNavigation();
        this.updateProgress();
        this.updateQuestionIndicators();
    }

    nextQuestion() {
        if (this.currentQuestion < this.questions.length - 1) {
            this.currentQuestion++;
            this.showQuestion(this.currentQuestion);
        }
    }

    prevQuestion() {
        if (this.currentQuestion > 0) {
            this.currentQuestion--;
            this.showQuestion(this.currentQuestion);
        }
    }

    updateNavigation() {
        const prevBtn = document.getElementById('prev-question');
        const nextBtn = document.getElementById('next-question');
        const submitBtn = document.getElementById('submit-quiz');

        if (prevBtn) {
            prevBtn.disabled = this.currentQuestion === 0;
        }

        if (nextBtn) {
            if (this.currentQuestion === this.questions.length - 1) {
                nextBtn.style.display = 'none';
            } else {
                nextBtn.style.display = 'inline-block';
            }
        }

        if (submitBtn) {
            submitBtn.style.display = this.currentQuestion === this.questions.length - 1 ? 'inline-block' : 'none';
        }
    }

    updateProgress() {
        const progressBar = document.getElementById('quiz-progress');
        const answeredCount = document.getElementById('answered-count');
        
        if (progressBar) {
            const progress = ((this.currentQuestion + 1) / this.questions.length) * 100;
            progressBar.style.width = `${progress}%`;
        }
        
        if (answeredCount) {
            const answered = Object.keys(this.answers).length;
            answeredCount.textContent = `${answered}/${this.questions.length}`;
        }
    }

    updateQuestionIndicators() {
        document.querySelectorAll('.question-indicator').forEach((indicator, index) => {
            indicator.classList.remove('active', 'status-answered', 'status-viewed-unanswered', 'status-not-viewed', 'status-current');

            if (index === this.currentQuestion) {
                indicator.classList.add('active', 'status-current');
            }

            const status = this.statuses[index];
            if (status === 'answered') {
                indicator.classList.add('status-answered');
            } else if (status === 'viewed_unanswered') {
                indicator.classList.add('status-viewed-unanswered');
            } else {
                indicator.classList.add('status-not-viewed');
            }
        });
    }

    submitAnswer() {
        const currentQuestionElement = this.questions[this.currentQuestion];
        const questionId = currentQuestionElement.dataset.questionId;
        const answerData = this.collectAnswer(currentQuestionElement);
        
        this.answers[questionId] = answerData;
        const qIndex = this.currentQuestion;
        this.statuses[qIndex] = 'answered';

        this.showAnswerFeedback(currentQuestionElement, answerData);
        this.updateQuestionIndicators();
    }

    collectAnswer(questionElement) {
        const questionType = questionElement.dataset.questionType;
        const answerData = {
            question_id: questionElement.dataset.questionId,
            answer_text: '',
            selected_choices: []
        };
        
        if (questionType === 'mcq_single' || questionType === 'mcq_multiple') {
            const selectedChoices = questionElement.querySelectorAll('input[type="checkbox"]:checked, input[type="radio"]:checked');
            answerData.selected_choices = Array.from(selectedChoices).map(input => input.value);
        } else if (questionType === 'true_false') {
            const selectedChoice = questionElement.querySelector('input[type="radio"]:checked');
            if (selectedChoice) {
                answerData.answer_text = selectedChoice.value;
            }
        } else {
            const textInput = questionElement.querySelector('input[type="text"], textarea');
            if (textInput) {
                answerData.answer_text = textInput.value;
            }
        }
        
        return answerData;
    }

    showAnswerFeedback(questionElement, answerData) {
        questionElement.classList.add('answered');
        
        const answeredCount = Object.keys(this.answers).length;
        const totalCount = this.questions.length;
        
        const counter = document.getElementById('answered-count');
        if (counter) {
            counter.textContent = `${answeredCount}/${totalCount}`;
        }
    }

    goToQuestion(index) {
        if (index < 0 || index >= this.questions.length) return;
        this.showQuestion(index);
    }

    async submitQuiz() {
        if (this._submitting) return;
        this._submitting = true;

        try {
            const submitNav = document.getElementById('submit-quiz');
            if (submitNav) submitNav.disabled = true;
            const modalConfirm = document.querySelector('#submitModal .btn-success');
            if (modalConfirm) {
                modalConfirm.disabled = true;
                modalConfirm.dataset.orig = modalConfirm.innerHTML;
                modalConfirm.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Submitting...';
            }
        } catch (e) {}

        try {
            const submitPromises = [];
            for (const [questionId, answerData] of Object.entries(this.answers)) {
                submitPromises.push(this.submitAnswerToServer(answerData));
            }
            await Promise.all(submitPromises);
        } catch (e) {
            console.error('One or more answer saves failed:', e);
        }

        const attemptId = document.getElementById('quiz-container')?.dataset.attemptId;
        if (!attemptId) {
            alert('Attempt information missing. Cannot submit quiz.');
            return;
        }

        try {
            const response = await fetch(`/finish-quiz/${attemptId}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                }
            });

            if (response.ok) {
                window.location.href = `/quiz-results/${attemptId}/`;
            } else {
                const data = await response.json().catch(() => null);
                alert((data && data.error) || 'Failed to submit quiz. Please try again.');
            }
        } catch (err) {
            console.error('Error finishing quiz:', err);
            alert('Network error while submitting quiz. Please try again.');
        }
    }

    async submitAnswerToServer(answerData) {
        try {
            const attemptId = document.getElementById('quiz-container')?.dataset.attemptId;
            const url = attemptId ? `/submit-answer/${attemptId}/` : '/submit-answer/';
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                },
                body: JSON.stringify(answerData)
            });
            
            return await response.json();
        } catch (error) {
            console.error('Error submitting answer:', error);
        }
    }
}

// Initialize global objects
window.quizTimer = new QuizTimer();
window.aiGenerator = new AIGenerator();
window.quizTaker = new QuizTaker();

// Initialize quiz taker if on quiz page
if (document.getElementById('quiz-container')) {
    window.quizTaker.init();
}

// Export helper functions
window.goToQuestion = function(index) {
    if (window.quizTaker) window.quizTaker.goToQuestion(index);
};

window.confirmSubmit = function() {
    if (window.quizTaker) window.quizTaker.submitQuiz();
};