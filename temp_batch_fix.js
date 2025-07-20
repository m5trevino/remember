       async function startBatchProcess() {
           if (!currentDatabase) {
               alert('Please select a database first');
               return;
           }
           
           if (selectedFiles.length === 0) {
               alert('Please select files to process first');
               return;
           }
           
           addMessage('system', `🚀 Starting batch processing on ${selectedFiles.length} selected files...`);
           addMessage('system', `📋 Using Service of Process Legal Context`);
           
           const requestData = {
               database: currentDatabase,
               files: selectedFiles,
               message: 'Perform comprehensive legal analysis focusing on service of process defects, procedural issues, and statutory violations.',
               provider: document.getElementById('provider-select').value,
               api_key: document.getElementById('api-key-select').value,
               context_mode: 'fresh',
               master_contexts: ['service_defects', 'tpa_violations', 'court_procedure']
           };
           
           try {
               addMessage('system', '⏳ Processing selected documents... This may take several minutes.');
               
               const response = await fetch('/api/chat', {
                   method: 'POST',
                   headers: {'Content-Type': 'application/json'},
                   body: JSON.stringify(requestData)
               });
               
               const data = await response.json();
               
               if (data.success) {
                   addMessage('assistant', data.response);
                   
                   // Auto-save the analysis
                   const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
                   const filename = `batch_legal_analysis_${timestamp}.md`;
                   
                   await saveAnalysis(data.response);
                   addMessage('system', `✅ Batch analysis completed and saved!`);
               } else {
                   addMessage('system', `❌ Batch processing failed: ${data.error}`);
               }
               
           } catch (error) {
               addMessage('system', `❌ Batch process error: ${error.message}`);
           }
       }
