async function api(url, opts={}){const r=await fetch(url,{headers:{'Content-Type':'application/json',...(opts.headers||{})},...opts});if(!r.ok){const t=await r.text();throw new Error(t)}return r.json()}
function busy(msg='Working…'){let e=document.getElementById('toast');if(!e){e=document.createElement('div');e.id='toast';e.style.cssText='position:fixed;right:24px;bottom:24px;background:#111827;color:#fff;padding:12px 16px;border-radius:10px;z-index:1000;font:13px system-ui;box-shadow:0 10px 30px #0004';document.body.appendChild(e)}e.textContent=msg;return e}
async function analyzeJob(id,reload=false){const t=busy('Running JD + policy + fit agents…');try{const x=await api(`/api/jobs/${id}/analyze`,{method:'POST'});t.textContent=`Fit ${x.fit_score}% · ${x.priority} · ${x.action}`;setTimeout(()=>{if(reload) location.reload();else location.reload()},650)}catch(e){t.textContent=e.message}}
async function analyzeAll(){const jobs=await api('/api/jobs');for(const j of jobs){busy(`Analyzing ${j.company}…`);await api(`/api/jobs/${j.id}/analyze`,{method:'POST'})}busy('Analysis complete');setTimeout(()=>location.reload(),600)}
async function prepareJob(id){const t=busy('Generating verified application package…');try{const x=await api(`/api/jobs/${id}/prepare`,{method:'POST'});t.textContent=`Package ready · ${x.review_reasons.length} review items`;setTimeout(()=>location.reload(),900)}catch(e){t.textContent=e.message}}
async function simulateApply(id){const t=busy('Launching Playwright browser agent against local mock ATS…');try{const x=await api(`/api/jobs/${id}/simulate-apply`,{method:'POST'});t.textContent=`Browser agent filled ${x.filled_fields.length} fields; paused for review`;setTimeout(()=>location.reload(),1200)}catch(e){t.textContent=e.message}}
async function addJob(){const data={company:document.getElementById('company').value,title:document.getElementById('title').value,location:document.getElementById('location').value,description:document.getElementById('description').value};const x=await api('/api/jobs/manual',{method:'POST',body:JSON.stringify(data)});await api(`/api/jobs/${x.job_id}/analyze`,{method:'POST'});location.href=`/jobs/${x.job_id}`}
function val(id){const v=document.getElementById(id)?.value;return v===''?null:v==='true'?true:v==='false'?false:v}
async function saveProfile(legal=false){const f=document.getElementById('profileForm');const fd=new FormData(f);let current=await api('/api/profile');const num=(x)=>x===''?null:Number(x);const data={...current,full_name:fd.get('full_name'),preferred_name:fd.get('preferred_name'),email:fd.get('email'),phone:fd.get('phone'),linkedin_url:fd.get('linkedin_url')||null,github_url:fd.get('github_url')||null,home_location:fd.get('home_location'),preferred_locations:String(fd.get('preferred_locations')||'').split('\n').map(x=>x.trim()).filter(Boolean),search_radius_miles:Number(fd.get('search_radius_miles')||50),remote_allowed:fd.get('remote_allowed')==='on',hybrid_allowed:fd.get('hybrid_allowed')==='on',onsite_allowed:fd.get('onsite_allowed')==='on',minimum_salary:num(fd.get('minimum_salary')),target_salary:num(fd.get('target_salary')),role_families:String(fd.get('role_families')).split('\n').map(x=>x.trim()).filter(Boolean),skills:String(fd.get('skills')).split('\n').map(x=>x.trim()).filter(Boolean)};['id','created_at','updated_at','legal_answers_verified_at','baseline_minutes','baseline_resume_filename','baseline_resume_path','baseline_resume_text','baseline_resume_uploaded_at'].forEach(k=>delete data[k]);if(legal){data.authorized_to_work_us=val('authorized');data.requires_current_sponsorship=val('sponsorNow');data.requires_future_sponsorship=val('sponsorFuture');data.work_authorization_type=document.getElementById('authType')?.value||null;data.work_authorization_expiration=document.getElementById('authExpiration')?.value||null}await api('/api/profile',{method:'PUT',body:JSON.stringify(data)});busy('Profile saved');setTimeout(()=>location.reload(),600)}

async function uploadMasterResume(){
  const file=document.getElementById('masterResume')?.files?.[0];
  if(!file){busy('Choose a PDF or DOCX resume first');return}
  const t=busy('Uploading and indexing your master resume…');
  const fd=new FormData(); fd.append('resume',file);
  try{
    const r=await fetch('/api/profile/resume',{method:'POST',body:fd});
    if(!r.ok) throw new Error(await r.text());
    const x=await r.json(); t.textContent=`Master resume saved · ${x.characters_extracted} characters indexed`; setTimeout(()=>location.reload(),900)
  }catch(e){t.textContent=e.message}
}

async function applyCareerOps(id){
  const ok=confirm('CareerOps will generate a tailored resume from your master resume, prepare the application, open the employer application in the browser agent, fill safe fields, upload the tailored files, and submit only if no sensitive/MFA/CAPTCHA review is detected. Continue?');
  if(!ok) return;
  const t=busy('CareerOps is preparing and applying…');
  try{
    const x=await api(`/api/jobs/${id}/apply-live?submit=true`,{method:'POST'});
    t.textContent=x.submitted?'Application submitted and tracked.':`Paused: ${x.manual_fields.length?x.manual_fields.join(', '):x.status}`;
    setTimeout(()=>location.reload(),1500)
  }catch(e){t.textContent=e.message}
}

async function scanNow(){
  const t=busy('Watchtower is scanning enabled sources…');
  try{const x=await api('/api/discover/run-configured',{method:'POST'});t.textContent=`Scan complete · ${x.fetched} fetched · ${x.created} new · ${x.analyzed} analyzed · ${x.location_filtered} location-filtered`;setTimeout(()=>location.reload(),1400)}catch(e){t.textContent=e.message}
}

async function addSource(){
  const fd=new FormData(); fd.append('source_type',document.getElementById('sourceType').value);fd.append('name',document.getElementById('sourceName').value);fd.append('token_or_url',document.getElementById('sourceToken').value);fd.append('enabled','true');fd.append('scan_interval_minutes','60');
  const t=busy('Adding live source…');try{const r=await fetch('/api/sources',{method:'POST',body:fd});if(!r.ok) throw new Error(await r.text());t.textContent='Source saved. Starting scan…';await api('/api/discover/run-configured',{method:'POST'});setTimeout(()=>location.reload(),1100)}catch(e){t.textContent=e.message}
}

async function saveAutopilot(){
  const fd=new FormData();fd.append('auto_apply_enabled',document.getElementById('autoApplyEnabled').checked?'true':'false');fd.append('auto_apply_min_fit',document.getElementById('autoApplyMinFit').value||'90');fd.append('max_auto_applications_per_day',document.getElementById('maxAutoApps').value||'5');
  const t=busy('Saving autopilot settings…');try{const r=await fetch('/api/runtime-settings',{method:'PUT',body:fd});if(!r.ok) throw new Error(await r.text());const x=await r.json();t.textContent=`Autopilot ${x.auto_apply_enabled?'enabled':'disabled'} · threshold ${x.auto_apply_min_fit}%`;setTimeout(()=>location.reload(),900)}catch(e){t.textContent=e.message}
}

async function verifyApplication(id){
  const t=busy('Checking stored submission evidence…');
  try{
    const x=await api(`/api/applications/${id}/verification`);
    if(x.state==='CONFIRMED') t.textContent=`Confirmed: employer acknowledgement detected${x.confirmation_term?` (“${x.confirmation_term}”)`:''}.`;
    else if(x.state==='UNVERIFIED') t.textContent='This record says submitted, but CareerOps has no employer confirmation evidence. Treat it as unverified.';
    else if(x.state==='REVIEW') t.textContent=`Human review required${x.manual_fields?.length?`: ${x.manual_fields.join(', ')}`:''}.`;
    else t.textContent='This application has not been submitted.';
  }catch(e){t.textContent=e.message}
}

async function updateApplicationStatus(id,status){
  if(!status) return;
  const t=busy(`Updating application to ${status}…`);
  try{const x=await api(`/api/applications/${id}/status?status=${encodeURIComponent(status)}`,{method:'PATCH'});t.textContent=`Application status updated to ${x.status}.`;setTimeout(()=>location.reload(),700)}catch(e){t.textContent=e.message}
}


async function addProfileLink(){
  const label=document.getElementById('linkLabel')?.value?.trim(); const url=document.getElementById('linkUrl')?.value?.trim(); const type=document.getElementById('linkType')?.value||'other';
  if(!label||!url){busy('Add a label and a complete URL');return}
  const fd=new FormData();fd.append('label',label);fd.append('url',url);fd.append('link_type',type);fd.append('include_in_applications','true');
  const t=busy('Saving link…');try{const r=await fetch('/api/profile/links',{method:'POST',body:fd});if(!r.ok)throw new Error(await r.text());t.textContent='Link added';setTimeout(()=>location.reload(),500)}catch(e){t.textContent=e.message}
}
async function deleteProfileLink(id){if(!confirm('Remove this link?'))return;const t=busy('Removing link…');try{await api(`/api/profile/links/${id}`,{method:'DELETE'});t.textContent='Link removed';setTimeout(()=>location.reload(),400)}catch(e){t.textContent=e.message}}

async function saveJournalEntry(){
  const required=['journalDate','journalTitle','journalBuilt']; if(required.some(id=>!document.getElementById(id)?.value?.trim())){busy('Date, title, and what you built are required');return}
  const fd=new FormData();
  const map={entry_date:'journalDate',title:'journalTitle',project:'journalProject',what_built:'journalBuilt',problem_solved:'journalProblem',architecture_decisions:'journalDecisions',tradeoffs:'journalTradeoffs',time_spent_hours:'journalHours',impact:'journalImpact',metrics_text:'journalMetrics',skills_text:'journalSkills',links_text:'journalLinks',lessons:'journalLessons'};
  for(const [k,id] of Object.entries(map)) fd.append(k,document.getElementById(id)?.value||'');
  const t=busy('Saving journal entry as candidate evidence…');try{const r=await fetch('/api/journal',{method:'POST',body:fd});if(!r.ok)throw new Error(await r.text());const x=await r.json();t.textContent=`Saved · evidence #${x.evidence_id}`;setTimeout(()=>location.reload(),700)}catch(e){t.textContent=e.message}
}
async function deleteJournalEntry(id){if(!confirm('Delete this journal entry and its linked candidate evidence?'))return;const t=busy('Deleting entry…');try{await api(`/api/journal/${id}`,{method:'DELETE'});t.textContent='Deleted';setTimeout(()=>location.reload(),500)}catch(e){t.textContent=e.message}}

async function saveReviewAnswer(applicationId, token){
  const q=document.getElementById(`reviewQuestion-${token}`)?.value||''; const answer=document.getElementById(`reviewAnswer-${token}`)?.value||''; const notes=document.getElementById(`reviewNotes-${token}`)?.value||'';
  const fd=new FormData();fd.append('question',q);fd.append('answer',answer);fd.append('notes',notes);fd.append('resolved','true');
  const t=busy('Saving verified application answer…');try{const r=await fetch(`/api/applications/${applicationId}/review-answer`,{method:'POST',body:fd});if(!r.ok)throw new Error(await r.text());const x=await r.json();t.textContent=x.remaining?`Saved · ${x.remaining} review item(s) left`:'Saved · application review cleared';setTimeout(()=>location.reload(),650)}catch(e){t.textContent=e.message}
}

async function saveNotificationSettings(){
  const fd=new FormData();
  const checks={enabled:'notificationsEnabled',notify_new_match:'notifyNewMatch',notify_high_fit:'notifyHighFit',notify_human_review:'notifyHumanReview',notify_submitted:'notifySubmitted',notify_failed:'notifyFailed',email_enabled:'emailEnabled',slack_enabled:'slackEnabled',discord_enabled:'discordEnabled',telegram_enabled:'telegramEnabled'};
  for(const [k,id] of Object.entries(checks)) fd.append(k,document.getElementById(id)?.checked?'true':'false');
  const vals={minimum_fit_score:'notifyMinFit',urgent_fit_score:'notifyUrgentFit',email_to:'emailTo',slack_webhook_url:'slackWebhook',discord_webhook_url:'discordWebhook',telegram_bot_token:'telegramToken',telegram_chat_id:'telegramChat'};
  for(const [k,id] of Object.entries(vals)) fd.append(k,document.getElementById(id)?.value||'');
  const t=busy('Saving notification settings…');
  try{const r=await fetch('/api/notifications/preferences',{method:'PUT',body:fd});if(!r.ok)throw new Error(await r.text());t.textContent='Notification settings saved';setTimeout(()=>location.reload(),600)}catch(e){t.textContent=e.message}
}
async function testNotification(){const t=busy('Sending test notification…');try{const x=await api('/api/notifications/test',{method:'POST'});t.textContent=x.ok?'Test event created. Check configured channels.':'Notifications are disabled.';setTimeout(()=>location.reload(),900)}catch(e){t.textContent=e.message}}
async function markNotificationRead(id){try{await api(`/api/notifications/${id}/read`,{method:'PATCH'});location.reload()}catch(e){busy(e.message)}}
async function ingestAlert(){
  const fd=new FormData();fd.append('provider',document.getElementById('alertProvider')?.value||'');fd.append('subject',document.getElementById('alertSubject')?.value||'');fd.append('text',document.getElementById('alertText')?.value||'');
  const t=busy('Importing job alert…');try{let r=await fetch('/api/alerts/email',{method:'POST',body:fd});if(!r.ok)throw new Error(await r.text());const x=await r.json();t.textContent=`Imported ${x.urls.length} job link(s); analyzing…`;await api('/api/alerts/process',{method:'POST'});setTimeout(()=>location.reload(),1000)}catch(e){t.textContent=e.message}
}
async function pollAlerts(){const t=busy('Polling configured alert inbox…');try{const imap=await api('/api/alerts/poll-imap',{method:'POST'});const processed=await api('/api/alerts/process',{method:'POST'});t.textContent=`IMAP imported ${imap.imported||0}; processed ${processed.messages||0} alert message(s); ${processed.created||0} jobs created`;setTimeout(()=>location.reload(),1100)}catch(e){t.textContent=e.message}}
async function toggleSource(id,enabled){const t=busy(`${enabled?'Enabling':'Disabling'} source…`);try{await api(`/api/sources/${id}?enabled=${enabled}`,{method:'PATCH'});t.textContent='Source updated';setTimeout(()=>location.reload(),500)}catch(e){t.textContent=e.message}}
async function deleteSource(id){if(!confirm('Remove this discovery source?'))return;const t=busy('Removing source…');try{await api(`/api/sources/${id}`,{method:'DELETE'});t.textContent='Source removed';setTimeout(()=>location.reload(),500)}catch(e){t.textContent=e.message}}
