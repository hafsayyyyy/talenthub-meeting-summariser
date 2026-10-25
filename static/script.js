
// TalentHub Meeting Summariser

document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("summaryForm");
    const fileInput = document.getElementById("transcriptFile");
    const browseButton = document.getElementById("browseButton");
    const dropZone = document.getElementById("dropZone");
    const fileName = document.getElementById("fileName");
    const transcriptInput = document.getElementById("transcript");

    const summariseButton = document.getElementById("summariseButton");
    const loading = document.getElementById("loading");
    const errorMessage = document.getElementById("errorMessage");

    const emptyState = document.getElementById("emptyState");
    const summaryResult = document.getElementById("summaryResult");
    const summaryList = document.getElementById("summaryList");
    const summaryTimestamp = document.getElementById("summaryTimestamp");
    const meetingId = document.getElementById("meetingId");
    const resultTitle = document.getElementById("resultTitle");

    const checklistItems = document.querySelectorAll(".quality-check");
    const progressBar = document.getElementById("progressBar");
    const progressText = document.getElementById("progressText");
    const saveChecklistButton = document.getElementById("saveChecklist");
    const saveMessage = document.getElementById("saveMessage");

    const CHECKLIST_KEY = "talenthub_quality_checklist";

    let selectedFile = null;

    // Open file picker
    browseButton.addEventListener("click", () => {
        fileInput.click();
    });

    // Handle selected file
    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) {
            selectedFile = fileInput.files[0];
            fileName.textContent = selectedFile.name;
            transcriptInput.value = "";
            hideError();
        }
    });

    // Allow drag and drop
    dropZone.addEventListener("dragover", (event) => {
        event.preventDefault();
        dropZone.classList.add("drag-over");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("drag-over");
    });

    dropZone.addEventListener("drop", (event) => {
        event.preventDefault();
        dropZone.classList.remove("drag-over");

        const file = event.dataTransfer.files[0];

        if (!file) {
            return;
        }

        if (!file.name.toLowerCase().endsWith(".txt")) {
            showError("Please upload a .txt transcript file.");
            return;
        }

        selectedFile = file;
        fileName.textContent = file.name;
        fileInput.value = "";
        transcriptInput.value = "";
        hideError();
    });

    // If the user starts typing, use the pasted transcript
    transcriptInput.addEventListener("input", () => {
        if (transcriptInput.value.trim()) {
            selectedFile = null;
            fileInput.value = "";
            fileName.textContent = "Using pasted transcript";
        } else if (!selectedFile) {
            fileName.textContent = "No file selected";
        }
    });

    // Submit transcript to FastAPI
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        hideError();
        saveMessage.textContent = "";

        const pastedTranscript = transcriptInput.value.trim();

        if (!selectedFile && !pastedTranscript) {
            showError("Please upload a .txt file or paste a transcript.");
            return;
        }

        const formData = new FormData();

        try {
            if (selectedFile) {
                if (!selectedFile.name.toLowerCase().endsWith(".txt")) {
                    showError("Please select a .txt transcript file.");
                    return;
                }

                const transcriptText = await selectedFile.text();

                if (!transcriptText.trim()) {
                    showError("The selected transcript file is empty.");
                    return;
                }

                formData.append("transcript", transcriptText);
            } else {
                formData.append("transcript", pastedTranscript);
            }

            // Show loading indicator
            summariseButton.disabled = true;
            loading.classList.remove("hidden");
            emptyState.classList.add("hidden");
            summaryResult.classList.add("hidden");

            const response = await fetch("/summarise", {
                method: "POST",
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    data.detail || data.error || "Unable to generate summary."
                );
            }

            if (!data.summary) {
                throw new Error("The API did not return a summary.");
            }

            displaySummary(data);

        } catch (error) {
            emptyState.classList.remove("hidden");
            showError(
                error.message ||
                "Something went wrong. Please try again."
            );
        } finally {
            summariseButton.disabled = false;
            loading.classList.add("hidden");
        }
    });

    // Display the returned summary
    function displaySummary(data) {
        summaryList.replaceChildren();

        let points = [];

        if (Array.isArray(data.summary)) {
            points = data.summary;
        } else if (typeof data.summary === "string") {
            points = data.summary
                .split(/\n+/)
                .map((line) => line.replace(/^\s*[-*•\d.)]+\s*/, "").trim())
                .filter(Boolean);
        } else if (
            data.summary &&
            typeof data.summary === "object"
        ) {
            points = Object.entries(data.summary).map(
                ([key, value]) => `${key}: ${
                    typeof value === "string"
                        ? value
                        : JSON.stringify(value)
                }`
            );
        }

        if (points.length === 0) {
            points = ["No summary points were returned."];
        }

        points.forEach((point) => {
            const item = document.createElement("li");
            item.textContent =
                typeof point === "string"
                    ? point
                    : JSON.stringify(point);
            summaryList.appendChild(item);
        });

        const title = document.getElementById("meetingTitle").value.trim();
        resultTitle.textContent = title || "Meeting Notes";

        summaryTimestamp.textContent = data.timestamp
            ? new Date(data.timestamp).toLocaleString()
            : new Date().toLocaleString();

        meetingId.textContent = data.meeting_id
            ? `Meeting ID: ${data.meeting_id}`
            : "";

        emptyState.classList.add("hidden");
        summaryResult.classList.remove("hidden");
    }

    // Display errors safely
    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.classList.remove("hidden");
    }

    function hideError() {
        errorMessage.textContent = "";
        errorMessage.classList.add("hidden");
    }

    // Update checklist progress
    function updateProgress() {
        const completed = Array.from(checklistItems)
            .filter((item) => item.checked).length;

        const percentage = (completed / checklistItems.length) * 100;

        progressBar.style.width = `${percentage}%`;
        progressText.textContent =
            `${completed} of ${checklistItems.length} checks completed`;
    }

    // Restore previously saved checklist
    function loadChecklist() {
        try {
            const savedData = JSON.parse(
                localStorage.getItem(CHECKLIST_KEY) || "{}"
            );

            checklistItems.forEach((item) => {
                item.checked = savedData[item.id] === true;
            });
        } catch (error) {
            console.error("Could not load saved checklist:", error);
        }

        updateProgress();
    }

    // Save checklist to browser storage
    saveChecklistButton.addEventListener("click", () => {
        const checklistData = {};

        checklistItems.forEach((item) => {
            checklistData[item.id] = item.checked;
        });

        try {
            localStorage.setItem(
                CHECKLIST_KEY,
                JSON.stringify(checklistData)
            );

            saveMessage.textContent = "Checklist saved successfully!";
        } catch (error) {
            saveMessage.textContent =
                "Unable to save checklist in this browser.";
        }
    });

    checklistItems.forEach((item) => {
        item.addEventListener("change", () => {
            updateProgress();
            saveMessage.textContent = "";
        });
    });

    // Initialise checklist on page load
    loadChecklist();
});
