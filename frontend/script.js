// Helpers for session state
const sessionState = {
    setCompany(company) { sessionStorage.setItem('company_name', company || ''); },
    getCompany() { return sessionStorage.getItem('company_name') || ''; },
    setModelName(model) { sessionStorage.setItem('product_name', model || ''); },
    getModelName() { return sessionStorage.getItem('product_name') || ''; },
    setModelId(id) { sessionStorage.setItem('db_id', id || ''); },
    getModelId() { return sessionStorage.getItem('db_id') || ''; },
    setFilename(name) { sessionStorage.setItem('filename', name || ''); },
    getFilename() { return sessionStorage.getItem('filename') || ''; },
};

document.getElementById('uploadBtn').addEventListener('click', async () => {
    const pdfInput = document.getElementById('pdfInput');
    const companyNameInput = document.getElementById('companyNameInput');
    const productCodeInput = document.getElementById('productCodeInput');
    const uploadStatus = document.getElementById('uploadStatus');
    const uploadBtn = document.getElementById('uploadBtn');
    const queryBtn = document.getElementById('queryBtn');

    if (!pdfInput.files.length) {
        uploadStatus.textContent = 'Please select a PDF file.';
        return;
    }

    const companyValue = companyNameInput.value.trim();
    const modelValue = productCodeInput.value.trim();

    if (!companyValue || !modelValue) {
        uploadStatus.textContent = 'Please enter Company and Model.';
        return;
    }

    uploadBtn.disabled = true;
    uploadStatus.textContent = 'Uploading...';

    const formData = new FormData();
    formData.append('file', pdfInput.files[0]);
    formData.append('company_name', companyValue);
    formData.append('product_code', modelValue);

    try {
        const response = await fetch('http://localhost:8000/upload_pdf/', {
            method: 'POST',
            body: formData
        });
        const result = await response.json();

        if (response.ok) {
            uploadStatus.textContent = result.message;
            uploadStatus.classList.add('text-green-600');
            // Save session info
            if (result.db_record) {
                sessionState.setCompany(result.db_record.company_name);
                sessionState.setModelName(result.db_record.product_code);
                sessionState.setModelId(result.db_record._id);
                sessionState.setFilename(result.db_record.uri || '');
            }
            queryBtn.disabled = false;
            // Refresh companies/models lists
            await populateCompanies();
            await populateModels(companyValue);
        } else {
            uploadStatus.textContent = result.detail || 'Upload failed.';
            uploadStatus.classList.add('text-red-600');
        }
    } catch (error) {
        uploadStatus.textContent = 'Error uploading PDF.';
        uploadStatus.classList.add('text-red-600');
    } finally {
        uploadBtn.disabled = false;
    }
});

// Populate companies dropdown
async function populateCompanies() {
    try {
        const res = await fetch('http://localhost:8000/companies/');
        const data = await res.json();
        const select = document.getElementById('companySelectMain');
        if (!select) return;
        
        select.innerHTML = '<option value="">-- Select company --</option>';
        (data.companies || []).forEach(c => {
            const opt = document.createElement('option');
            opt.value = c;
            opt.textContent = c;
            if (c === sessionState.getCompany()) opt.selected = true;
            select.appendChild(opt);
        });
    } catch (e) {
        console.error('Failed to load companies', e);
    }
}

// Populate models for a company
async function populateModels(company) {
    const select = document.getElementById('modelSelectMain');
    if (!select) return;
    
    select.innerHTML = '<option value="">-- Select model --</option>';
    if (!company) return;
    
    try {
        const res = await fetch(`http://localhost:8000/companies/${encodeURIComponent(company)}/models/`);
        const data = await res.json();
         (data.models || []).forEach(m => {
             const opt = document.createElement('option');
             opt.value = m.product_code || m.product_name || 'Unknown';
             opt.textContent = `${m.product_code || m.product_name || 'Unknown'} (${m.filename || 'file'})`;
             opt.dataset.dbId = m._id;
             opt.dataset.filename = m.filename || '';
             select.appendChild(opt);
         });
    } catch (e) {
        console.error('Failed to load models', e);
    }
}

// React to company selection to load models
document.getElementById('companySelectMain').addEventListener('change', async (e) => {
    const company = e.target.value;
    sessionState.setCompany(company);
    await populateModels(company);
    document.getElementById('queryBtn').disabled = !company;
});

// React to model selection to store id
document.getElementById('modelSelectMain').addEventListener('change', (e) => {
    const opt = e.target.selectedOptions[0];
    if (!opt) return;
    sessionState.setModelName(opt.value);
    sessionState.setModelId(opt.dataset.dbId || '');
    sessionState.setFilename(opt.dataset.filename || '');
    document.getElementById('queryBtn').disabled = !opt.value;
});

document.getElementById('queryBtn').addEventListener('click', async () => {
    const queryInput = document.getElementById('queryInput');
    const responseOutput = document.getElementById('responseOutput');
    const queryBtn = document.getElementById('queryBtn');

    if (!queryInput.value.trim()) {
        responseOutput.innerHTML = '<p class="text-sm text-red-500">Please enter a question.</p>';
        return;
    }

    queryBtn.disabled = true;
    responseOutput.innerHTML = '<p class="text-sm text-gray-500">Processing...</p>';

    try {
        const response = await fetch('http://localhost:8000/query/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: queryInput.value,
                company_name: sessionState.getCompany() || document.getElementById('companyNameInput').value.trim() || null,
                product_code: sessionState.getModelName() || null,
            })
        });
        const result = await response.json();

        if (response.ok) {
            responseOutput.innerHTML = `<p class="text-sm text-gray-800">${result.response.replace(/\n/g, '<br>')}</p>`;
        } else {
            responseOutput.innerHTML = `<p class="text-sm text-red-500">${result.detail || 'Query failed.'}</p>`;
        }
    } catch (error) {
        responseOutput.innerHTML = '<p class="text-sm text-red-500">Error processing query.</p>';
    } finally {
        queryBtn.disabled = false;
        queryInput.value = '';
    }
});

// Initial bootstrap
window.addEventListener('load', async () => {
    await populateCompanies();
    const company = sessionState.getCompany();
    if (company) await populateModels(company);
});