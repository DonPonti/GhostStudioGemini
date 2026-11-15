const $ = id => document.getElementById(id);
let currentFile = null;
let currentPlan = null;
async function api(url, options={}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Request failed");
  return data;
}
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
async function refreshStatus() {
  try {
    const s = await api("/api/status");
    $("connection").textContent = (s.ffmpeg ? "● FFmpeg ready" : "● FFmpeg missing") + (s.gemini_configured ? " · Gemini connected" : " · Add Gemini API key in .env");
    $("connection").style.color = s.ffmpeg ? "#c5f36b" : "#ff9b83";
  } catch { $("connection").textContent = "Local engine unavailable"; }
}
const dz = $("dropzone");
$("videoFile").addEventListener("change", e => { if (e.target.files[0]) upload(e.target.files[0]); });
dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("drag"); });
dz.addEventListener("dragleave", () => dz.classList.remove("drag"));
dz.addEventListener("drop", e => { e.preventDefault(); dz.classList.remove("drag"); if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
async function upload(file) {
  $("mediaInfo").classList.remove("hidden");
  $("mediaInfo").textContent = "Uploading to your local studio…";
  try {
    const body = new FormData(); body.append("file", file);
    const result = await api("/api/upload", {method:"POST", body});
    currentFile = result.filename;
    $("mediaInfo").textContent = file.name + " · " + (result.size_bytes/1048576).toFixed(1) + " MB · Inspecting…";
    const probe = await api("/api/probe/" + encodeURIComponent(currentFile));
    const fmt = probe.format || {};
    const video = (probe.streams || []).find(s => s.codec_type === "video") || {};
    const duration = Number(fmt.duration || 0);
    $("mediaInfo").innerHTML = "<strong>" + escapeHtml(file.name) + "</strong><br>" + (video.width||"?") + " × " + (video.height||"?") + " · " + duration.toFixed(1) + " sec · " + escapeHtml(video.codec_name||"unknown codec");
    $("trimEnd").value = duration ? duration.toFixed(1) : "";
    $("analyzeBtn").disabled = false; $("renderBtn").disabled = false;
  } catch(err) { $("mediaInfo").textContent = "Upload / inspection error: " + err.message; }
}
$("analyzeBtn").addEventListener("click", async () => {
  if (!currentFile) return;
  const btn = $("analyzeBtn"); btn.disabled = true; btn.textContent = "Gemini is analyzing your footage…";
  try {
    const result = await api("/api/analyze", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({filename:currentFile,context:$("context").value,target:$("target").value,duration_seconds:Number($("duration").value)})});
    currentPlan = result.plan; showPlan(currentPlan);
  } catch(err) { alert(err.message); }
  finally { btn.disabled = !currentFile; btn.innerHTML = "✦ &nbsp; Build my edit plan <span>→</span>"; }
});
function showPlan(plan) {
  $("emptyState").classList.add("hidden"); $("planView").classList.remove("hidden");
  const segments = (plan.segments || []).filter(s => s.keep !== false);
  let html = '<div class="plan-title">' + escapeHtml(plan.project_title || "Your edit blueprint") + '</div><p class="plan-copy">' + escapeHtml(plan.creative_direction || "") + '</p><button class="small-btn" id="downloadPlan">↓ Download JSON edit plan</button>';
  segments.forEach((s,i) => {
    html += '<div class="segment"><div class="segment-top"><span>' + String(i+1).padStart(2,"0") + ' · ' + escapeHtml(s.purpose||"moment") + '</span><span>' + Number(s.source_start||0).toFixed(1) + 's — ' + Number(s.source_end||0).toFixed(1) + 's</span></div><p>' + escapeHtml(s.visual_note||"") + '</p><p>' + escapeHtml(s.editing_note||"") + '</p></div>';
  });
  html += '<div class="segment"><div class="segment-top">CAPTION DIRECTION</div><p>' + escapeHtml(plan.caption_style||"Not specified") + '</p></div>';
  $("planView").innerHTML = html;
  $("downloadPlan").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(plan,null,2)],{type:"application/json"});
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "ghost-studio-edit-plan.json"; a.click(); URL.revokeObjectURL(a.href);
  });
}
$("renderBtn").addEventListener("click", async () => {
  if (!currentFile) return;
  const btn = $("renderBtn"); btn.disabled = true; btn.textContent = "Rendering locally…";
  $("renderResult").textContent = "FFmpeg is creating your rough cut. Longer videos may take a while.";
  try {
    const start = Number($("trimStart").value || 0);
    const end = $("trimEnd").value === "" ? null : Number($("trimEnd").value);
    const result = await api("/api/render",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({filename:currentFile,start_seconds:start,end_seconds:end})});
    $("renderResult").innerHTML = 'Render ready · <a style="color:#c5f36b" href="' + result.download_url + '">Download MP4 ↗</a>';
  } catch(err) { $("renderResult").textContent = "Render failed: " + err.message; }
  finally { btn.disabled = !currentFile; btn.innerHTML = 'Render selected range <span>↗</span>'; }
});
refreshStatus();