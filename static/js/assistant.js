document.addEventListener('DOMContentLoaded', function() {
    const chatForm = document.getElementById('chatForm');
    const chatInput = document.getElementById('chatInput');

    if (chatForm && chatInput) {
        chatForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const text = chatInput.value.trim();
            if (!text) return;
            sendChatMessage(text);
            chatInput.value = '';
        });
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
    typingBubble.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2 text-primary"></i> Consulting project database & risk engine...';
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
        
        // Simple markdown formatter
        let formatted = formatMarkdown(data.response || 'No response available.');
        assistantBubble.innerHTML = `
            <div class="d-flex align-items-center gap-2 mb-2 pb-1 border-bottom">
                <i class="fa-solid fa-robot text-primary"></i>
                <strong class="text-primary small">ProjectPulse AI</strong>
                <span class="badge bg-success bg-opacity-10 text-success ms-auto" style="font-size: 0.65rem;">Grounded DB Response</span>
            </div>
            <div>${formatted}</div>
        `;
        chatMessages.appendChild(assistantBubble);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    })
    .catch(err => {
        typingBubble.remove();
        const errBubble = document.createElement('div');
        errBubble.className = 'chat-bubble assistant-bubble text-danger';
        errBubble.innerHTML = '<i class="fa-solid fa-circle-exclamation me-1"></i> An error occurred while retrieving project intelligence. Please try again.';
        chatMessages.appendChild(errBubble);
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.innerText = text;
    return div.innerHTML;
}

function formatMarkdown(text) {
    // 1. Sanitize/escape raw HTML first to prevent any script execution (Requirement 20)
    let safe = escapeHtml(text || '');
    // 2. Safe Markdown transformations
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
