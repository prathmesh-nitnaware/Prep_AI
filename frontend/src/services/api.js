
import axios from "axios";

/**
 * BASE URL SWITCHER
 * Swaps between local development and production Render deployment.
 */
const getApiUrl = () => {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  if (typeof window !== "undefined" && (window.location.port === "5173" || window.location.port === "5174")) {
    return "http://localhost:5000";
  }
  return "";
};

export const getWebSocketUrl = (path = "/api/v1/interview/stream") => {
  if (typeof window === "undefined") return "";
  const isHttps = window.location.protocol === "https:";
  const protocol = isHttps ? "wss:" : "ws:";
  const host = window.location.host;
  if (window.location.port === "5173" || window.location.port === "5174") {
    return `ws://localhost:5000${path}`;
  }
  return `${protocol}//${host}${path}`;
};

const API_URL = getApiUrl();


/**
 * AXIOS CLIENT CONFIGURATION
 */
const apiClient = axios.create({
  baseURL: API_URL,
  timeout: 60000,
  headers: {
    "Content-Type": "application/json",
  },
});

/**
 * AUTH INTERCEPTOR
 * Automatically attaches the JWT Bearer token to every request if it exists.
 */
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token && token !== "undefined" && token !== "null") {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

/**
 * RESPONSE INTERCEPTOR
 * Handles automatic logout if the backend returns a 401 Unauthorized (token expired).
 */
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      console.warn("Session expired. Logging out.");
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      window.location.href = "/login";
    }

    // Global error banner
    const msg = error.response?.data?.error || error.response?.data?.message || error.message || "An unexpected error occurred.";
    const banner = document.createElement("div");
    banner.style.cssText = "position:fixed; top:20px; right:20px; background:#ef4444; color:white; padding:12px 24px; border-radius:6px; z-index:9999; box-shadow:0 4px 6px rgba(0,0,0,0.1); font-family:sans-serif; transition: opacity 0.3s;";
    banner.innerText = msg;
    document.body.appendChild(banner);
    setTimeout(() => {
      banner.style.opacity = '0';
      setTimeout(() => banner.remove(), 300);
    }, 5000);

    return Promise.reject(
      error.response?.data || { message: "Server error" }
    );
  }
);

// ==========================================
// API ACTIONS
// ==========================================

export const api = {
  /**
   * AUTHENTICATION
   */
  loginUser: async (credentials) => {
    const res = await apiClient.post("/api/auth/login", credentials);
    if (res.data.token) {
      localStorage.setItem("token", res.data.token);
      localStorage.setItem("user", JSON.stringify(res.data.user));
    }
    return res.data;
  },

  registerUser: async (userData) => {
    const res = await apiClient.post("/api/auth/signup", userData);
    return res.data;
  },

  loginWithGoogle: async (googlePayload) => {
    const res = await apiClient.post("/api/auth/google", googlePayload);
    if (res.data.token) {
      localStorage.setItem("token", res.data.token);
      localStorage.setItem("user", JSON.stringify(res.data.user));
    }
    return res.data;
  },

  /**
   * RESUME VAULT (Persistent MongoDB Storage)
   * Stores the resume once for use across all AI modules.
   */
  uploadProfileResume: async (file) => {
    const formData = new FormData();
    formData.append("resume", file);
    const res = await apiClient.post("/api/profile/resume/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data;
  },

  /**
   * INTERVIEW RESUME UPLOAD 
   * (Alias for scoreResume used in the setup screen)
   */
  uploadResumeForInterview: async (file) => {
    const formData = new FormData();
    formData.append("resume", file);
    const res = await apiClient.post("/api/resume/score", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data;
  },

  /**
   * RESUME SCORING (ATS Optimizer)
   */
  scoreResume: async (formData) => {
    const res = await apiClient.post("/api/resume/score", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data;
  },

  /**
   * CODING DOJO (HackerRank logic)
   * Fetches curated challenges from the coding routes.
   */
  getChallenges: async () => {
    const res = await apiClient.get("/api/coding/challenges");
    return res.data;
  },

  getSingleChallenge: async (id) => {
    const res = await apiClient.get(`/api/coding/challenge/${id}`);
    return res.data;
  },

  /**
   * MOCK INTERVIEW SESSIONS
   */
  initiateInterview: async (payload) => {
    const res = await apiClient.post("/api/interview/initiate", payload);
    return res.data;
  },

  submitAnswer: async (payload) => {
    const res = await apiClient.post("/api/interview/submit", payload);
    return res.data;
  },

  getNextQuestion: async (payload) => {
    const res = await apiClient.post("/api/interview/next", payload);
    return res.data;
  },

  submitCode: async (payload) => {
    // Allows submission context for both Live Interviews and Coding Dojo
    const res = await apiClient.post("/api/interview/submit", payload);
    return res.data;
  },

  /**
   * ANALYTICS & DASHBOARD
   */
  getDashboard: async () => {
    const res = await apiClient.get("/api/dashboard/");
    return res.data;
  },

  client: apiClient
};