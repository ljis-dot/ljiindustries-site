(function(){var m=document.getElementById('b-media');if(!m)return;
var data=JSON.parse(document.getElementById('b-data').textContent);
function fmt(t){t=Math.max(0,Math.floor(t||0));return Math.floor(t/60)+':'+('0'+t%60).slice(-2);}
function go(t){m.currentTime=t;var p=m.play();if(p&&p.catch)p.catch(function(){});}
document.querySelectorAll('[data-start]').forEach(function(b){b.addEventListener('click',function(){go(parseFloat(b.dataset.start));if(m.tagName==='VIDEO'&&b.classList.contains('b-listen')){m.scrollIntoView({block:'center',behavior:'smooth'});}});});
var play=document.getElementById('b-play'),seek=document.getElementById('b-seek'),tm=document.getElementById('b-time');
if(play){play.addEventListener('click',function(){if(m.paused){go(m.currentTime);}else{m.pause();}});
 m.addEventListener('play',function(){play.innerHTML='&#10074;&#10074;';play.setAttribute('aria-label','Pause');});
 m.addEventListener('pause',function(){play.innerHTML='&#9654;';play.setAttribute('aria-label','Play');});
 seek.addEventListener('input',function(){m.currentTime=parseFloat(seek.value);});}
var marks=[].slice.call(document.querySelectorAll('.b-chapters button')).map(function(b){return{t:parseFloat(b.dataset.start),e:parseFloat(b.dataset.end),id:b.dataset.story,el:b};});
var panel=document.getElementById('b-panel'),shown;
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function render(id){if(!panel||id===shown)return;shown=id;var s=data.stories[id];if(!s){panel.hidden=true;panel.dataset.story='';return;}
 var chips=(s.outlets||[]).map(function(o){return o.url?'<a class="b-chip" target="_blank" rel="noopener nofollow" href="'+esc(o.url)+'">'+esc(o.name)+'</a>':'<span class="b-chip">'+esc(o.name)+'</span>';}).join('');
 var offs=(s.officialSources||[]).map(function(u){return '<a target="_blank" rel="noopener nofollow" href="'+esc(u)+'">'+esc(u.replace(/^https?:\/\/(www\.)?/,'').split('/')[0])+'</a>';}).join(' ');
 panel.innerHTML='<div class="b-meta"><span class="eyebrow">'+esc(s.kicker)+'</span><span class="b-badge '+esc(s.badgeClass)+'">'+esc(s.badge)+'</span></div><h2 class="b-head">'+esc(s.headline)+'</h2>'+(s.summary?'<p class="b-sum">'+esc(s.summary)+'</p>':'')+(s.why?'<p class="b-why"><strong>Why it matters to the US:</strong> '+esc(s.why)+'</p>':'')+(s.statusNote?'<p class="b-note">'+esc(s.statusNote)+'</p>':'')+'<div class="b-chips">'+chips+'</div>'+(offs?'<p class="b-off">Checked against: '+offs+'</p>':'');
 panel.hidden=false;panel.dataset.story=id;}
m.addEventListener('timeupdate',function(){var t=m.currentTime,cur=null;
 marks.forEach(function(k){if(t>=k.t-0.05&&(!(k.e>k.t)||t<k.e))cur=k;});
 if(!cur)marks.forEach(function(k){if(t>=k.t-0.05)cur=k;});
 marks.forEach(function(k){k.el.classList.toggle('on',k===cur);});
 var id=cur&&cur.id||null;
 document.querySelectorAll('.b-story').forEach(function(s){s.classList.toggle('playing',!!id&&id===s.dataset.story);});
 render(id);
 if(seek&&document.activeElement!==seek)seek.value=t;
 if(tm)tm.textContent=fmt(t)+' / '+fmt(isFinite(m.duration)?m.duration:parseFloat(seek&&seek.max));});
})();
