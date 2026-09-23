document.addEventListener('DOMContentLoaded', function() {
    const chatForm = document.getElementById('chatForm');
    const chatInput = document.getElementById('chatInput');
    const micBtn = document.getElementById('micBtn');
    const micIcon = document.getElementById('micIcon');
    const voiceReadoutToggle = document.getElementById('voiceReadoutToggle');

    if (chatForm && chatInput) {
        chatForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const text = chatInput.value.trim();
            if (!text) return;
            sendChatMessage(text);
            chatInput.value = '';
        });
    }

    // Web Speech API Voice Recognition
    if (micBtn && micIcon) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SpeechRecognition) {
            const recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.interimResults = false;
            recognition.lang = 'en-IN'; // Indian English default, also understands standard terms

            let isRecording = false;

            micBtn.addEventListener('click', function() {
                if (isRecording) {
                    recognition.stop();
                } else {
                    try {
                        recognition.start();
                    } catch (err) {
                        console.error('Speech recognition start error:', err);
                    }
                }
            });

            recognition.onstart = function() {
                isRecording = true;
                micBtn.classList.remove('btn-outline-secondary');
                micBtn.classList.add('btn-danger');
                micIcon.className = 'fa-solid fa-microphone text-white fa-beat';
                chatInput.placeholder = 'Listening... Please speak your infrastructure query now.';
            };

            recognition.onresult = function(event) {
                const speechResult = event.results[0][0].transcript;
                if (speechResult) {
                    chatInput.value = speechResult;
                    sendChatMessage(speechResult);
                    chatInput.value = '';
                }
            };

            recognition.onerror = function(event) {
                console.warn('Speech recognition error:', event.error);
                resetMic();
            };

            recognition.onend = function() {
                resetMic();
            };

            function resetMic() {
                isRecording = false;
                micBtn.classList.remove('btn-danger');
                micBtn.classList.add('btn-outline-secondary');
                micIcon.className = 'fa-solid fa-microphone';
                chatInput.placeholder = 'Ask about contractors, delays, material tests, or speak using the microphone...';
            }
        } else {
            micBtn.title = 'Speech recognition not supported on this browser';
            micBtn.classList.add('disabled');
        }
    }
});

let currentAssistantMode = 'chat';

function setAssistantMode(mode) {
    currentAssistantMode = mode;

    // Update active button classes
    const modeButtons = document.querySelectorAll('#assistantModeGroup .mode-btn');
    modeButtons.forEach(btn => {
        if (btn.getAttribute('data-mode') === mode) {
            btn.classList.remove('btn-outline-secondary');
            btn.classList.add('btn-primary', 'active');
        } else {
            btn.classList.remove('btn-primary', 'active');
            btn.classList.add('btn-outline-secondary');
        }
    });

    // Toggle prompt chips containers
    const allPromptContainers = document.querySelectorAll('.mode-prompts');
    allPromptContainers.forEach(container => container.classList.add('d-none'));

    const targetContainer = document.getElementById(`prompts-${mode}`);
    if (targetContainer) {
        targetContainer.classList.remove('d-none');
    }

    // Update labels and placeholders
    const titleEl = document.getElementById('promptModeTitle');
    const inputEl = document.getElementById('chatInput');
    if (titleEl && inputEl) {
        if (mode === 'voice') {
            titleEl.textContent = 'Voice Query Suggestions (Tap Microphone or Speak)';
            inputEl.placeholder = 'Click the microphone to speak your query aloud, or type here...';
            // Trigger microphone if available
            const micBtn = document.getElementById('micBtn');
            if (micBtn && !micBtn.classList.contains('disabled')) {
                micBtn.click();
            }
        } else if (mode === 'data') {
            titleEl.textContent = 'Analytical Telemetry & Statistical Diagnostics';
            inputEl.placeholder = 'Request delay vs cost correlation, TreeSHAP attributions, or sector variance...';
        } else if (mode === 'docs') {
            titleEl.textContent = 'Statutory Documents & Certificate Queries';
            inputEl.placeholder = 'Search statutory clearance certificates, EIA orders, or lab test documents...';
        } else {
            titleEl.textContent = 'Frequently Asked Intelligence Inquiries';
            inputEl.placeholder = 'Ask about contractors, delays, material tests, or enter project code...';
        }
    }
}

function submitPrompt(promptText) {
    sendChatMessage(promptText);
}

function sendChatMessage(messageText) {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;

    // 1. Append User Message with Mode Badge
    const userBubble = document.createElement('div');
    userBubble.className = 'chat-bubble user-bubble';
    
    let modeBadge = '';
    if (currentAssistantMode === 'data') {
        modeBadge = '<span class="badge bg-light text-primary me-2 font-monospace" style="font-size: 0.68rem;">📊 DATA MODE</span>';
    } else if (currentAssistantMode === 'docs') {
        modeBadge = '<span class="badge bg-light text-warning-emphasis me-2 font-monospace" style="font-size: 0.68rem;">📄 DOCS MODE</span>';
    } else if (currentAssistantMode === 'voice') {
        modeBadge = '<span class="badge bg-light text-danger me-2 font-monospace" style="font-size: 0.68rem;">🎙️ VOICE MODE</span>';
    }

    userBubble.innerHTML = `${modeBadge}${escapeHtml(messageText)}`;
    chatMessages.appendChild(userBubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // 2. Append Typing Indicator
    const typingBubble = document.createElement('div');
    typingBubble.className = 'chat-bubble assistant-bubble typing-indicator';
    
    let typingMsg = 'Consulting official database, contractor records & BIS test results...';
    if (currentAssistantMode === 'data') {
        typingMsg = 'Calculating regressions, TreeSHAP attributions & outlier metrics...';
    } else if (currentAssistantMode === 'docs') {
        typingMsg = 'Searching statutory document repository & verifying tamper hashes...';
    } else if (currentAssistantMode === 'voice') {
        typingMsg = 'Synthesizing voice response from live ground telemetry...';
    }

    typingBubble.innerHTML = `<i class="fa-solid fa-spinner fa-spin me-2 text-primary"></i> ${typingMsg}`;
    chatMessages.appendChild(typingBubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // 3. Request API
    fetch('/api/assistant', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            query: messageText,
            mode: currentAssistantMode
        })
    })
    .then(res => res.json())
    .then(data => {
        typingBubble.remove();
        const assistantBubble = document.createElement('div');
        assistantBubble.className = 'chat-bubble assistant-bubble shadow-sm';
        
        let rawResponse = data.response || 'No response available.';
        let formatted = formatMarkdown(rawResponse);

        let badgeLabel = 'Grounded Official Data';
        let badgeClass = 'bg-success bg-opacity-10 text-success';
        if (data.mode === 'data') {
            badgeLabel = 'Statistical Regression Engine';
            badgeClass = 'bg-primary bg-opacity-10 text-primary';
        } else if (data.mode === 'docs') {
            badgeLabel = 'Verified Document Repository';
            badgeClass = 'bg-warning bg-opacity-10 text-warning-emphasis';
        } else if (data.mode === 'voice') {
            badgeLabel = 'Voice Synthesis Output';
            badgeClass = 'bg-danger bg-opacity-10 text-danger';
        }

        assistantBubble.innerHTML = `
            <div class="d-flex align-items-center gap-2 mb-2 pb-1 border-bottom">
                <i class="fa-solid fa-robot text-primary"></i>
                <strong class="text-primary small">Web-Based Integrated Project-Monitoring Platform</strong>
                <span class="badge ${badgeClass} ms-auto" style="font-size: 0.65rem;">${badgeLabel}</span>
                <button type="button" class="btn btn-sm btn-link p-0 text-muted ms-2" onclick="speakResponse(this)" title="Read aloud">
                    <i class="fa-solid fa-volume-high"></i>
                </button>
            </div>
            <div class="response-text-content">${formatted}</div>
        `;
        chatMessages.appendChild(assistantBubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        // Auto-readout if Voice Readout Toggle is on or if in voice mode
        const readoutToggle = document.getElementById('voiceReadoutToggle');
        if ((readoutToggle && readoutToggle.checked) || currentAssistantMode === 'voice') {
            speakText(rawResponse);
        }
    })
    .catch(err => {
        typingBubble.remove();
        const errBubble = document.createElement('div');
        errBubble.className = 'chat-bubble assistant-bubble text-danger';
        errBubble.innerHTML = '<i class="fa-solid fa-circle-exclamation me-1"></i> An error occurred while retrieving project intelligence. Please try again.';
        chatMessages.appendChild(errBubble);
    });
}

function speakResponse(btn) {
    const parent = btn.closest('.chat-bubble');
    if (!parent) return;
    const textEl = parent.querySelector('.response-text-content');
    if (textEl) {
        speakText(textEl.innerText);
    }
}

function speakText(rawText) {
    if (!('speechSynthesis' in window)) return;
    
    // Cancel any ongoing speech
    window.speechSynthesis.cancel();

    // Clean text of markdown tokens for natural speech
    let clean = (rawText || '')
        .replace(/#+/g, '')
        .replace(/\*+/g, '')
        .replace(/`+/g, '')
        .replace(/-+/g, '')
        .replace(/\[.*?\]\(.*?\)/g, '')
        .replace(/₹/g, 'Rupees ')
        .replace(/Cr/g, 'Crores')
        .replace(/km/g, 'kilometers')
        .trim();

    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    // Pick English (Indian) or standard English voice if available
    const voices = window.speechSynthesis.getVoices();
    const preferredVoice = voices.find(v => v.lang.includes('en-IN') || v.lang.includes('en-GB') || v.lang.includes('en-US'));
    if (preferredVoice) {
        utterance.voice = preferredVoice;
    }

    window.speechSynthesis.speak(utterance);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.innerText = text;
    return div.innerHTML;
}

function formatMarkdown(text) {
    let safe = escapeHtml(text || '');
    let html = safe
        .replace(/^### (.*$)/gim, '<h6 class="fw-bold text-dark mt-2 mb-1">$1</h6>')
        .replace(/^#### (.*$)/gim, '<div class="fw-bold text-dark small mt-2 mb-1">$1</div>')
        .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/gim, '<em>$1</em>')
        .replace(/`([^`]+)`/gim, '<code class="bg-light text-primary px-1 rounded font-monospace small">$1</code>')
        .replace(/^- (.*$)/gim, '<div class="ps-3 mb-1">&bull; $1</div>')
        .replace(/\n\n/g, '<br><br>')
        .replace(/\n/g, '<br>');
    return html;
}
