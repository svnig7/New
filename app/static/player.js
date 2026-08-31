(function () {
  function fmt(t) {
    if (!isFinite(t)) return "0:00";
    const m = Math.floor(t / 60);
    const s = Math.floor(t % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  }

  class FusedPlayer {
    constructor(root, tracks) {
      this.root = root;
      this.video = root.querySelector("video");
      this.tracks = tracks || { audio: [], subs: [] };
      this.altAudio = null;
      this._buildControls();
      this._buildAudioTracks();
      this._buildSubTracks();
      this._bind();
    }

    _buildControls() {
      const c = document.createElement("div");
      c.className = "fp-controls";
      c.innerHTML = `
        <button class="fp-btn fp-play" title="Play/Pause">&#9654;</button>
        <span class="fp-time fp-cur">0:00</span>
        <div class="fp-progress"><div class="fp-progress-fill"></div></div>
        <span class="fp-time fp-dur">0:00</span>
        ${this.tracks.audio.length ? '<div class="fp-menu fp-audio-menu"><button class="fp-btn" title="Audio track">&#128266;</button><div class="fp-menu-panel"></div></div>' : ""}
        ${this.tracks.subs.length ? '<div class="fp-menu fp-subs-menu"><button class="fp-btn" title="Subtitles">&#128172;</button><div class="fp-menu-panel"></div></div>' : ""}
        <button class="fp-btn fp-fullscreen" title="Fullscreen">&#9974;</button>
      `;
      this.root.appendChild(c);
      this.controls = c;
    }

    _buildAudioTracks() {
      if (!this.tracks.audio.length) return;
      const panel = this.controls.querySelector(".fp-audio-menu .fp-menu-panel");
      const opts = [{ label: "Original", url: null }, ...this.tracks.audio];
      opts.forEach((opt, i) => {
        const item = document.createElement("div");
        item.className = "fp-menu-item" + (i === 0 ? " active" : "");
        item.textContent = opt.label;
        item.onclick = () => this._selectAudio(opt, item);
        panel.appendChild(item);
      });
    }

    _selectAudio(opt, item) {
      this.controls.querySelectorAll(".fp-audio-menu .fp-menu-item").forEach((el) => el.classList.remove("active"));
      item.classList.add("active");
      if (this.altAudio) {
        this.altAudio.pause();
        this.altAudio.remove();
        this.altAudio = null;
      }
      if (!opt.url) {
        this.video.muted = false;
        return;
      }
      this.video.muted = true;
      const a = new Audio(opt.url);
      a.currentTime = this.video.currentTime;
      if (!this.video.paused) a.play().catch(() => {});
      this.altAudio = a;
    }

    _buildSubTracks() {
      if (!this.tracks.subs.length) return;
      const panel = this.controls.querySelector(".fp-subs-menu .fp-menu-panel");
      const opts = [{ label: "Off", url: null }, ...this.tracks.subs];
      opts.forEach((opt, i) => {
        const item = document.createElement("div");
        item.className = "fp-menu-item" + (i === 0 ? " active" : "");
        item.textContent = opt.label;
        item.onclick = () => this._selectSub(opt, item);
        panel.appendChild(item);
      });
    }

    _selectSub(opt, item) {
      this.controls.querySelectorAll(".fp-subs-menu .fp-menu-item").forEach((el) => el.classList.remove("active"));
      item.classList.add("active");
      Array.from(this.video.querySelectorAll("track")).forEach((t) => t.remove());
      if (!opt.url) return;
      const track = document.createElement("track");
      track.kind = "subtitles";
      track.label = opt.label;
      track.src = opt.url;
      track.default = true;
      this.video.appendChild(track);
      setTimeout(() => {
        if (this.video.textTracks[0]) this.video.textTracks[0].mode = "showing";
      }, 50);
    }

    _bind() {
      const v = this.video;
      const playBtn = this.controls.querySelector(".fp-play");
      const progress = this.controls.querySelector(".fp-progress");
      const fill = this.controls.querySelector(".fp-progress-fill");
      const cur = this.controls.querySelector(".fp-cur");
      const dur = this.controls.querySelector(".fp-dur");
      const fsBtn = this.controls.querySelector(".fp-fullscreen");

      playBtn.onclick = () => (v.paused ? v.play() : v.pause());
      v.addEventListener("click", () => (v.paused ? v.play() : v.pause()));
      v.addEventListener("play", () => {
        playBtn.innerHTML = "&#10074;&#10074;";
        if (this.altAudio) this.altAudio.play().catch(() => {});
      });
      v.addEventListener("pause", () => {
        playBtn.innerHTML = "&#9654;";
        if (this.altAudio) this.altAudio.pause();
      });
      v.addEventListener("loadedmetadata", () => {
        dur.textContent = fmt(v.duration);
      });
      v.addEventListener("timeupdate", () => {
        cur.textContent = fmt(v.currentTime);
        fill.style.width = (v.duration ? (v.currentTime / v.duration) * 100 : 0) + "%";
        if (this.altAudio && Math.abs(this.altAudio.currentTime - v.currentTime) > 0.35) {
          this.altAudio.currentTime = v.currentTime;
        }
      });
      progress.onclick = (e) => {
        const rect = progress.getBoundingClientRect();
        const pct = (e.clientX - rect.left) / rect.width;
        v.currentTime = pct * v.duration;
        if (this.altAudio) this.altAudio.currentTime = v.currentTime;
      };
      fsBtn.onclick = () => {
        if (document.fullscreenElement) document.exitFullscreen();
        else this.root.requestFullscreen().catch(() => {});
      };
      this.root.querySelectorAll(".fp-menu").forEach((menu) => {
        menu.querySelector(".fp-btn").onclick = (e) => {
          e.stopPropagation();
          const wasOpen = menu.classList.contains("open");
          this.root.querySelectorAll(".fp-menu.open").forEach((m) => m.classList.remove("open"));
          if (!wasOpen) menu.classList.add("open");
        };
      });
      document.addEventListener("click", () => {
        this.root.querySelectorAll(".fp-menu.open").forEach((m) => m.classList.remove("open"));
      });
      this.root.addEventListener("mousemove", () => this.root.classList.add("fp-active"));
    }
  }

  window.FusedPlayer = FusedPlayer;
})();
