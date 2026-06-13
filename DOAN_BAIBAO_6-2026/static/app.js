// Global State
let selectedImageFile = null;

// DOM Elements
const chatFeed = document.getElementById("chatFeed");
const userInput = document.getElementById("userInput");
const inputForm = document.getElementById("inputForm");
const sendBtn = document.getElementById("sendBtn");
const imageInput = document.getElementById("imageInput");
const imagePreviewContainer = document.getElementById("imagePreviewContainer");
const imagePreview = document.getElementById("imagePreview");
const previewFilename = document.getElementById("previewFilename");
const clearImagePreviewBtn = document.getElementById("clearImagePreview");

// Sidebar elements
const noDiagnosisData = document.getElementById("noDiagnosisData");
const diagnosisResult = document.getElementById("diagnosisResult");
const diseaseSeverity = document.getElementById("diseaseSeverity");
const diseaseName = document.getElementById("diseaseName");
const diseaseId = document.getElementById("diseaseId");
const fusionScore = document.getElementById("fusionScore");
const fusionScoreFill = document.getElementById("fusionScoreFill");
const matchedFeaturesList = document.getElementById("matchedFeaturesList");
const locationsList = document.getElementById("locationsList");
const treatmentList = document.getElementById("treatmentList");
const complicationsList = document.getElementById("complicationsList");
const breakdownList = document.getElementById("breakdownList");

// Status indicator
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");

// Settings
const settingsToggle = document.getElementById("settingsToggle");
const settingsDropdown = document.getElementById("settingsDropdown");
const geminiApiKeyInput = document.getElementById("geminiApiKey");
const saveApiKeyBtn = document.getElementById("saveApiKey");
const apiKeyStatus = document.getElementById("apiKeyStatus");

// ==========================================
// INITIALIZATION
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    // Initialize Lucide icons
    lucide.createIcons();
    
    // Check local storage for API Key
    const savedKey = localStorage.getItem("gemini_api_key");
    if (savedKey) {
        geminiApiKeyInput.value = savedKey;
        apiKeyStatus.textContent = "✓ Đã tải API Key từ bộ nhớ";
        apiKeyStatus.style.color = "var(--color-success)";
    }
    
    // Check server status
    checkServerStatus();
    
    // Polling status until ready
    const statusInterval = setInterval(async () => {
        const isReady = await checkServerStatus();
        if (isReady) {
            clearInterval(statusInterval);
        }
    }, 5000);
});

// Check API health status
async function checkServerStatus() {
    try {
        const res = await fetch("/api/status");
        if (res.ok) {
            const data = await res.json();
            if (data.status === "ready") {
                statusDot.className = "dot pulse green";
                statusText.textContent = "Hệ thống sẵn sàng";
                return true;
            } else {
                statusDot.className = "dot pulse orange";
                statusText.textContent = "Đang khởi tạo cơ sở dữ liệu...";
            }
        }
    } catch (e) {
        statusDot.className = "dot pulse orange";
        statusText.textContent = "Không kết nối được server";
    }
    return false;
}

// ==========================================
// SETTINGS DROPDOWN EVENT HANDLERS
// ==========================================
settingsToggle.addEventListener("click", (e) => {
    e.stopPropagation();
    settingsDropdown.classList.toggle("hidden");
    settingsToggle.classList.toggle("active");
});

document.addEventListener("click", (e) => {
    if (!settingsDropdown.classList.contains("hidden") && !settingsDropdown.contains(e.target) && e.target !== settingsToggle) {
        settingsDropdown.classList.add("hidden");
        settingsToggle.classList.remove("active");
    }
});

saveApiKeyBtn.addEventListener("click", () => {
    const key = geminiApiKeyInput.value.trim();
    if (key) {
        localStorage.setItem("gemini_api_key", key);
        apiKeyStatus.textContent = "✓ Lưu API Key thành công!";
        apiKeyStatus.style.color = "var(--color-success)";
    } else {
        localStorage.removeItem("gemini_api_key");
        apiKeyStatus.textContent = "Đã xóa API Key";
        apiKeyStatus.style.color = "var(--text-secondary)";
    }
    setTimeout(() => {
        settingsDropdown.classList.add("hidden");
        settingsToggle.classList.remove("active");
    }, 1000);
});

// ==========================================
// IMAGE UPLOAD & PREVIEW
// ==========================================
imageInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) {
        selectedImageFile = file;
        previewFilename.textContent = file.name;
        
        const reader = new FileReader();
        reader.onload = (event) => {
            imagePreview.src = event.target.result;
            imagePreviewContainer.classList.remove("hidden");
        };
        reader.readAsDataURL(file);
    }
});

clearImagePreviewBtn.addEventListener("click", () => {
    selectedImageFile = null;
    imageInput.value = "";
    imagePreviewContainer.classList.add("hidden");
    imagePreview.src = "";
});

// ==========================================
// CHAT LOGIC
// ==========================================
inputForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const query = userInput.value.trim();
    
    if (!query && !selectedImageFile) return;
    
    // Render user message
    renderUserMessage(query, selectedImageFile);
    
    // Clear input fields
    userInput.value = "";
    const imgToSend = selectedImageFile;
    
    // Clear image preview
    selectedImageFile = null;
    imageInput.value = "";
    imagePreviewContainer.classList.add("hidden");
    
    // Show typing indicator
    const typingIndicator = showTypingIndicator();
    
    // Prepare FormData
    const formData = new FormData();
    formData.append("query", query || "Phân tích hình ảnh nốt tổn thương da.");
    if (imgToSend) {
        formData.append("image", imgToSend);
    }
    
    // Get Gemini Key header
    const headers = {};
    const api_key = localStorage.getItem("gemini_api_key");
    if (api_key) {
        headers["x-gemini-key"] = api_key;
    }
    
    // Send API Request
    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: headers,
            body: formData
        });
        
        // Remove typing indicator
        typingIndicator.remove();
        
        if (response.ok) {
            const data = await response.json();
            
            // Render Bot Response
            renderBotMessage(data.response);
            
            // Update Diagnosis Dashboard
            updateDiagnosisDashboard(data);
        } else {
            const err = await response.json();
            renderBotMessage(`⚠️ Lỗi máy chủ: ${err.detail || "Không thể thực hiện chẩn đoán lúc này."}`);
        }
    } catch (e) {
        typingIndicator.remove();
        renderBotMessage("⚠️ Lỗi kết nối: Không thể gửi yêu cầu đến server. Vui lòng kiểm tra cổng kết nối.");
    }
});

function renderUserMessage(text, file) {
    const msgDiv = document.createElement("div");
    msgDiv.className = "message user-msg";
    
    let bubbleContent = "";
    if (file) {
        const tempUrl = URL.createObjectURL(file);
        bubbleContent += `<img src="${tempUrl}" class="msg-image" alt="Uploaded Image">`;
    }
    if (text) {
        bubbleContent += `<p>${escapeHTML(text)}</p>`;
    }
    
    msgDiv.innerHTML = `
        <div class="avatar"><i data-lucide="user"></i></div>
        <div class="msg-bubble">${bubbleContent}</div>
    `;
    
    chatFeed.appendChild(msgDiv);
    lucide.createIcons({node: msgDiv});
    scrollToBottom();
}

function showTypingIndicator() {
    const msgDiv = document.createElement("div");
    msgDiv.className = "message bot-msg typing-msg";
    msgDiv.innerHTML = `
        <div class="avatar"><i data-lucide="bot"></i></div>
        <div class="msg-bubble">
            <div class="typing">
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
                <span class="typing-dot"></span>
            </div>
        </div>
    `;
    chatFeed.appendChild(msgDiv);
    lucide.createIcons({node: msgDiv});
    scrollToBottom();
    return msgDiv;
}

function renderBotMessage(markdownText) {
    const msgDiv = document.createElement("div");
    msgDiv.className = "message bot-msg";
    
    const formattedHtml = parseMarkdown(markdownText);
    
    msgDiv.innerHTML = `
        <div class="avatar"><i data-lucide="bot"></i></div>
        <div class="msg-bubble">${formattedHtml}</div>
    `;
    
    chatFeed.appendChild(msgDiv);
    lucide.createIcons({node: msgDiv});
    scrollToBottom();
}

// ==========================================
// RENDER HELPERS
// ==========================================
function escapeHTML(str) {
    return str.replace(/[&<>'"]/g, 
        tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
}

function parseMarkdown(text) {
    // Simple markdown parsing for bold, lists, alerts
    let html = escapeHTML(text);
    
    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*(.*?)\*/g, "<em>$1</em>");
    
    // Convert newlines to breaks, handling bullet lists
    const lines = html.split("\n");
    let inList = false;
    let listHtml = "";
    
    const parsedLines = lines.map(line => {
        // Bullet list
        if (line.trim().startsWith("- ") || line.trim().startsWith("* ")) {
            const cleanLine = line.replace(/^[\s-*]+/, "").trim();
            if (!inList) {
                inList = true;
                return `<ul><li>${cleanLine}</li>`;
            }
            return `<li>${cleanLine}</li>`;
        } else {
            let prefix = "";
            if (inList) {
                inList = false;
                prefix = "</ul>";
            }
            return prefix + (line.trim() ? `<p>${line}</p>` : "");
        }
    });
    
    let finalHtml = parsedLines.join("");
    if (inList) {
        finalHtml += "</ul>";
    }
    
    // Replace warning blocks/emojis
    finalHtml = finalHtml.replace(/(⚠️.*?<\/p>)/g, '<span class="warning-alert-small">$1</span>');
    
    return finalHtml;
}

function scrollToBottom() {
    chatFeed.scrollTop = chatFeed.scrollHeight;
}

// ==========================================
// DIAGNOSIS VIEW LOGIC
// ==========================================
function updateDiagnosisDashboard(data) {
    noDiagnosisData.classList.add("hidden");
    diagnosisResult.classList.remove("hidden");
    
    const exp = data.explanation;
    
    // 1. Severity Badge
    const sev = exp.severity.toLowerCase();
    diseaseSeverity.textContent = exp.severity;
    diseaseSeverity.className = "severity-badge"; // reset
    if (sev === "low" || sev === "benign") {
        diseaseSeverity.classList.add("severity-low");
    } else if (sev === "medium" || sev === "warning") {
        diseaseSeverity.classList.add("severity-medium");
    }
    // defaults to red (high/critical)
    
    // 2. Names & Score
    diseaseName.textContent = exp.disease_name;
    diseaseId.textContent = exp.disease_id;
    
    const scorePct = Math.round(exp.score * 100);
    fusionScore.textContent = `${scorePct}%`;
    fusionScoreFill.style.width = `${scorePct}%`;
    
    // 3. Lists matching
    renderTags(matchedFeaturesList, exp.matched_features);
    renderTags(locationsList, exp.common_locations);
    renderList(treatmentList, exp.first_line_treatment);
    
    // Complications panel highlight if exists
    if (exp.complications && exp.complications.length > 0) {
        document.querySelector(".alert-card").classList.remove("hidden");
        renderList(complicationsList, exp.complications);
    } else {
        document.querySelector(".alert-card").classList.add("hidden");
    }
    
    // 4. Breakdown chart
    renderBreakdownChart(data.scores);
}

function renderTags(ulElement, items) {
    ulElement.innerHTML = "";
    if (items && items.length > 0) {
        items.forEach(item => {
            const li = document.createElement("li");
            li.textContent = item;
            ulElement.appendChild(li);
        });
    } else {
        ulElement.innerHTML = `<li>Không ghi nhận</li>`;
    }
}

function renderList(ulElement, items) {
    ulElement.innerHTML = "";
    if (items && items.length > 0) {
        items.forEach(item => {
            const li = document.createElement("li");
            li.textContent = item;
            ulElement.appendChild(li);
        });
    } else {
        ulElement.innerHTML = `<li>Không ghi nhận</li>`;
    }
}

function renderBreakdownChart(scores) {
    breakdownList.innerHTML = "";
    
    // Sort scores descending
    const sorted = Object.entries(scores).sort((a, b) => b[1] - a[1]);
    
    // Map disease ID to Full Name
    const names = {
        "AKIEC": "Actinic Keratosis",
        "BCC": "Basal Cell Carcinoma",
        "BKL": "Benign Keratosis",
        "DF": "Dermatofibroma",
        "MEL": "Melanoma",
        "NV": "Melanocytic Nevus",
        "VASC": "Vascular Lesion"
    };
    
    sorted.forEach(([dId, val]) => {
        const pct = Math.round(val * 100);
        const itemDiv = document.createElement("div");
        itemDiv.className = "breakdown-item";
        itemDiv.innerHTML = `
            <div class="item-info">
                <span>${names[dId] || dId} (${dId})</span>
                <strong>${pct}%</strong>
            </div>
            <div class="mini-progress">
                <div class="mini-fill" style="width: ${pct}%"></div>
            </div>
        `;
        breakdownList.appendChild(itemDiv);
    });
}
