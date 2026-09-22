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

function submitPrompt(promptText) {
    sendChatMessage(promptText);
}

function sendChatMessage(messageText) {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;

    // 1. Append User Message
    const userBubble = document.createElement('div');
    userBubble.className = 'chat-bubble user-bubble';
    userBubble.innerHTML = escapeHtml(messageText);
    chatMessages.appendChild(userBubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // 2. Append Typing Indicator
    const typingBubble = document.createElement('div');
    typingBubble.className = 'chat-bubble assistant-bubble typing-indicator';
    typingBubble.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2 text-primary"></i> Consulting official database, contractor records & BIS test results...';
    chatMessages.appendChild(typingBubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // 3. Request API
    fetch('/api/assistant', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: messageText })
    })
    .then(res => res.json())
    .then(data => {
        typingBubble.remove();
        const assistantBubble = document.createElement('div');
        assistantBubble.className = 'chat-bubble assistant-bubble shadow-sm';
        
        let rawResponse = data.response || 'No response available.';
        let formatted = formatMarkdown(rawResponse);

        assistantBubble.innerHTML = `
            <div class="d-flex align-items-center gap-2 mb-2 pb-1 border-bottom">
                <i class="fa-solid fa-robot text-primary"></i>
                <strong class="text-primary small">ProjectPulse AI</strong>
                <span class="badge bg-success bg-opacity-10 text-success ms-auto" style="font-size: 0.65rem;">Grounded Official Data</span>
                <button type="button" class="btn btn-sm btn-link p-0 text-muted ms-2" onclick="speakResponse(this)" title="Read aloud">
                    <i class="fa-solid fa-volume-high"></i>
                </button>
            </div>
            <div class="response-text-content">${formatted}</div>
        `;
        chatMessages.appendChild(assistantBubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        // Auto-readout if Voice Readout Toggle is on
        const readoutToggle = document.getElementById('voiceReadoutToggle');
        if (readoutToggle && readoutToggle.checked) {
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
