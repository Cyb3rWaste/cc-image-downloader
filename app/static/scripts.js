const DEFAULT_COLUMN = (document.body && document.body.dataset && document.body.dataset.defaultColumn) || "1000image";
const CSV_ACTION_LABEL = "Download & Convert CSV Images";

const state = {
    folderKey: null,
    csvToken: null,
    csvColumns: [],
    selectedColumn: DEFAULT_COLUMN,
    pendingCsvName: null,
    hasRecentUpload: false
};

const dropZone = document.getElementById('dropZone');
const dropInput = document.getElementById('dropInput');
const dropHint = document.getElementById('dropHint');
const csvAction = document.getElementById('csvAction');
const keepPngToggle = document.getElementById('keepPng');
const enhanceNamesToggle = document.getElementById('enhanceNames');
const qualitySlider = document.getElementById('quality');
const qualityValue = document.getElementById('qualityValue');
const advancedToggle = document.getElementById('advancedToggle');
const advancedPanel = document.getElementById('advancedPanel');
const folderInfo = document.getElementById('folderInfo');
const statusMessage = document.getElementById('statusMessage');
const statusDetails = document.getElementById('statusDetails');
const columnSelect = document.getElementById('columnSelect');

const defaultHint = dropHint.textContent;

function setDropzoneState(stateName) {
    dropZone.classList.remove('dragover', 'file-selected', 'invalid');
    if (stateName) {
        dropZone.classList.add(stateName);
        return;
    }
    if (state.csvToken || state.hasRecentUpload) {
        dropZone.classList.add('file-selected');
    }
}

function showMessage(message, type = 'info', details) {
    statusMessage.textContent = message;
    statusMessage.className = `status-message ${type}`;
    statusMessage.style.display = 'block';

    if (Array.isArray(details) && details.length) {
        statusDetails.innerHTML = '';
        details.forEach((item) => {
            const li = document.createElement('li');
            li.textContent = item;
            statusDetails.appendChild(li);
        });
        statusDetails.style.display = 'block';
    } else {
        statusDetails.innerHTML = '';
        statusDetails.style.display = 'none';
    }
}

function updateFolderInfo(result) {
    if (result && result.folder_key) {
        state.folderKey = result.folder_key;
    }
    if (folderInfo) {
        folderInfo.textContent = '';
        folderInfo.hidden = true;
    }
}

function resetCsvState() {
    state.csvToken = null;
    state.csvColumns = [];
    state.selectedColumn = DEFAULT_COLUMN;
    state.pendingCsvName = null;
    state.hasRecentUpload = false;
    columnSelect.innerHTML = '<option value="">Upload a CSV to choose a column</option>';
    columnSelect.disabled = true;
    csvAction.disabled = true;
    setButtonLoading(csvAction, false, CSV_ACTION_LABEL);
    setDropzoneState(null);
    dropHint.textContent = defaultHint;
}

function renderColumnOptions(columns, defaultColumn) {
    columnSelect.innerHTML = '';
    if (!Array.isArray(columns) || !columns.length) {
        columnSelect.innerHTML = '<option value="">No columns detected</option>';
        columnSelect.disabled = true;
        return;
    }

    const preferred = defaultColumn && columns.includes(defaultColumn) ? defaultColumn : columns[0];
    columns.forEach((column) => {
        const option = document.createElement('option');
        option.value = column;
        option.textContent = column;
        if (column === preferred) {
            option.selected = true;
        }
        columnSelect.appendChild(option);
    });
    columnSelect.disabled = false;
    state.selectedColumn = preferred;
}

function setButtonLoading(button, isLoading, label) {
    if (isLoading) {
        button.disabled = true;
        button.innerHTML = `<span class="loading-spinner"></span>${label}`;
    } else {
        button.disabled = false;
        button.textContent = label;
    }
}

qualitySlider.addEventListener('input', () => {
    qualityValue.textContent = qualitySlider.value;
});

advancedToggle.addEventListener('click', () => {
    const isHidden = advancedPanel.hasAttribute('hidden');
    if (isHidden) {
        advancedPanel.removeAttribute('hidden');
        advancedToggle.setAttribute('aria-expanded', 'true');
    } else {
        advancedPanel.setAttribute('hidden', '');
        advancedToggle.setAttribute('aria-expanded', 'false');
    }
});

columnSelect.addEventListener('change', (event) => {
    state.selectedColumn = event.target.value || DEFAULT_COLUMN;
});

csvAction.addEventListener('click', async () => {
    if (!state.csvToken) {
        state.hasRecentUpload = false;
        showMessage('Upload a CSV first to download images.', 'error');
        setDropzoneState('invalid');
        return;
    }
    await processCsv();
});

['dragenter', 'dragover'].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        setDropzoneState('dragover');
    });
});

['dragleave', 'dragend'].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (state.csvToken || state.hasRecentUpload) {
            setDropzoneState('file-selected');
        } else {
            setDropzoneState(null);
        }
    });
});

dropZone.addEventListener('click', () => dropInput.click());
dropZone.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        dropInput.click();
    }
});

dropZone.addEventListener('drop', (event) => {
    event.preventDefault();
    event.stopPropagation();
    const files = event.dataTransfer.files;
    if (files && files.length) {
        handleFiles(files);
    } else if (state.csvToken || state.hasRecentUpload) {
        setDropzoneState('file-selected');
    } else {
        setDropzoneState(null);
    }
});

dropInput.addEventListener('change', (event) => {
    const files = event.target.files;
    if (files && files.length) {
        handleFiles(files);
        dropInput.value = '';
    }
});

function classifyFiles(fileList) {
    const csvFiles = [];
    const imageFiles = [];
    const unsupported = [];

    Array.from(fileList).forEach((file) => {
        const extension = file.name.split('.').pop()?.toLowerCase();
        if (extension === 'csv') {
            csvFiles.push(file);
        } else if (file.type.startsWith('image/')) {
            imageFiles.push(file);
        } else {
            unsupported.push(file.name);
        }
    });

    return { csvFiles, imageFiles, unsupported };
}

async function handleFiles(fileList) {
    const { csvFiles, imageFiles, unsupported } = classifyFiles(fileList);

    if (unsupported.length) {
        state.hasRecentUpload = false;
        showMessage(`Unsupported file(s): ${unsupported.join(', ')}`, 'error');
        setDropzoneState('invalid');
        return;
    }

    if (csvFiles.length && imageFiles.length) {
        state.hasRecentUpload = false;
        showMessage('Please drop either CSV files or images, not both at once.', 'error');
        setDropzoneState('invalid');
        return;
    }

    if (csvFiles.length > 1) {
        state.hasRecentUpload = false;
        showMessage('Please upload one CSV at a time.', 'error');
        setDropzoneState('invalid');
        return;
    }

    if (csvFiles.length) {
        await prepareCsv(csvFiles[0]);
        return;
    }

    if (imageFiles.length) {
        await uploadImages(imageFiles);
    }
}

async function prepareCsv(file) {
    const formData = new FormData();
    formData.append('file', file);
    showMessage('Analysing CSV...', 'info');
    dropHint.textContent = `Analysing ${file.name}...`;
    setDropzoneState('file-selected');

    try {
        const response = await fetch('/csv/prepare', {
            method: 'POST',
            body: formData
        });
        const result = await response.json();

        if (!response.ok) {
            state.hasRecentUpload = false;
            showMessage(result.error || 'Failed to analyse CSV.', 'error');
            dropHint.textContent = defaultHint;
            setDropzoneState('invalid');
            return;
        }

        state.csvToken = result.token;
        state.csvColumns = result.columns || [];
        state.pendingCsvName = result.filename || file.name;

        renderColumnOptions(state.csvColumns, result.default_column || DEFAULT_COLUMN);
        csvAction.disabled = false;
        state.hasRecentUpload = true;

        dropHint.textContent = `Ready: ${state.pendingCsvName}. Choose a column and download.`;
        showMessage(`CSV ready: ${state.pendingCsvName}.`, 'success', ['Select the column then press the download button.']);
        setDropzoneState('file-selected');
    } catch (error) {
        state.hasRecentUpload = false;
        showMessage(`An unexpected error occurred: ${error.message}`, 'error');
        dropHint.textContent = defaultHint;
        setDropzoneState('invalid');
    }
}

async function processCsv() {
    const payload = {
        token: state.csvToken,
        column: state.selectedColumn,
        quality: parseInt(qualitySlider.value, 10),
        keep_png: keepPngToggle.checked,
        enhance_filenames: enhanceNamesToggle ? enhanceNamesToggle.checked : false
    };

    setButtonLoading(csvAction, true, 'Processing...');
    showMessage('Downloading and converting images...', 'info');

    try {
        const response = await fetch('/csv/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json();

        const details = [];
        if (Array.isArray(result.processed)) {
            details.push(`Processed: ${result.processed.length} image(s).`);
        }
        if (Array.isArray(result.skipped) && result.skipped.length) {
            details.push(`Skipped: ${result.skipped.length} item(s).`);
        }
        if (result.note) {
            details.push(result.note);
        }

        const type = response.ok ? (result.processed && result.processed.length ? 'success' : 'info') : 'error';
        const message = response.ok ? result.message : (result.error || 'Failed to process CSV.');
        showMessage(message, type, details);

        if (response.ok) {
            updateFolderInfo(result);
            resetCsvState();
        } else {
            state.hasRecentUpload = false;
            setDropzoneState('invalid');
        }
    } catch (error) {
        state.hasRecentUpload = false;
        showMessage(`An unexpected error occurred: ${error.message}`, 'error');
        setDropzoneState('invalid');
    } finally {
        setButtonLoading(csvAction, false, CSV_ACTION_LABEL);
    }
}

async function uploadImages(imageFiles) {
    const formData = new FormData();
    imageFiles.forEach((file) => formData.append('images', file));
    formData.append('quality', qualitySlider.value);
    formData.append('keep_png', keepPngToggle.checked);
    if (enhanceNamesToggle) {
        formData.append('enhance_filenames', enhanceNamesToggle.checked);
    }
    if (state.folderKey) {
        formData.append('folder_key', state.folderKey);
    }

    showMessage('Uploading and processing images...', 'info');
    dropHint.textContent = `${imageFiles.length} file(s) uploading...`;

    try {
        const response = await fetch('/upload-images', {
            method: 'POST',
            body: formData
        });
        const result = await response.json();

        const details = [];
        if (Array.isArray(result.processed)) {
            details.push(`Processed: ${result.processed.length} image(s).`);
        }
        if (Array.isArray(result.skipped) && result.skipped.length) {
            details.push(`Skipped: ${result.skipped.length} item(s).`);
        }
        if (result.note) {
            details.push(result.note);
        }

        const type = response.ok ? (result.message_type || 'success') : 'error';
        const message = response.ok ? result.message : (result.error || 'Image upload failed.');
        showMessage(message, type, details);

        if (response.ok) {
            updateFolderInfo(result);
            dropHint.textContent = 'Images processed. Drop more files to continue.';
            state.hasRecentUpload = true;
            setDropzoneState('file-selected');
        } else {
            dropHint.textContent = defaultHint;
            state.hasRecentUpload = false;
            setDropzoneState('invalid');
        }
    } catch (error) {
        state.hasRecentUpload = false;
        showMessage(`An unexpected error occurred: ${error.message}`, 'error');
        dropHint.textContent = defaultHint;
        setDropzoneState('invalid');
    }
}

showMessage('Drop a CSV or images to get started.', 'info');
