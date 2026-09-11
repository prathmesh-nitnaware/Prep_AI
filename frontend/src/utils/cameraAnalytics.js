/**
 * frontend/src/utils/cameraAnalytics.js
 * =======================================
 * Deterministic Camera & Observable Video Delivery Analytics Engine for PrepAI.
 * 
 * CORE PRINCIPLES:
 * 1. Measures OBSERVABLE behavioral signals only (face presence, framing, gaze alignment, movement stability).
 * 2. ZERO psychological or emotional inferences (no claims of nervousness, lying, confidence, or deception).
 * 3. Temporal smoothing and hysteresis to prevent single-frame spikes from skewing metrics.
 * 4. Hardware resilience: Missing/denied camera produces 'unavailable' status without penalizing candidate scoring.
 * 5. All video processing remains strictly client-side in the browser. Zero video frames are uploaded or persisted.
 */

import * as faceapi from '@vladmandic/face-api';

export const CAMERA_CONFIG = {
  sampleIntervalMs: 200,            // 5 FPS sampling rate for optimal CPU & detection balance
  scoreThreshold: 0.5,              // Minimum detector confidence threshold
  inputSize: 224,                   // TinyFaceDetector input dimensions
  framingBounds: {                  // Recommended quadrant for face center
    minX: 0.20,
    maxX: 0.80,
    minY: 0.15,
    maxY: 0.85,
  },
  faceSizeBounds: {                 // Face bounding box area relative to video frame
    minAreaRatio: 0.03,             // Face too small / far from camera
    maxAreaRatio: 0.70,             // Face too close to camera
  },
  sustainedGazeDeviationFrames: 4,  // ~800ms sustained deviation before counting looking away
  excessiveMovementThreshold: 0.08, // Normalized Euclidean displacement between frames
  multipleFaceThreshold: 2,         // Multiple face detection threshold
};

export class CameraAnalyticsEngine {
  constructor() {
    this.modelsLoaded = false;
    this.isAnalyzing = false;
    this.analysisInterval = null;
    this.cameraAvailability = "unavailable"; // 'available' | 'unavailable' | 'denied'

    // Temporal tracking state
    this.totalFrames = 0;
    this.facePresentFrames = 0;
    this.properFramingFrames = 0;
    this.lookingAwayFrames = 0;
    this.excessiveMovementFrames = 0;
    this.multipleFaceFrames = 0;

    this.lastFaceCenter = null;
    this.movementDeltas = [];
    this.consecutiveLookingAwayCount = 0;

    // Real-time HUD states
    this.currentFacePresent = false;
    this.currentLookingAway = false;
    this.currentFramingValid = true;
    this.currentPostureStability = 100;
  }

  /**
   * Loads Face API models (TinyFaceDetector and FaceLandmarks).
   */
  async loadModels(modelBasePath = "/models") {
    if (this.modelsLoaded) return true;
    try {
      await faceapi.nets.tinyFaceDetector.loadFromUri(modelBasePath);
      this.modelsLoaded = true;
      return true;
    } catch (err) {
      if (process.env.NODE_ENV !== "production") {
        console.warn("Face API models could not be loaded from local URI:", err);
      }
      this.modelsLoaded = false;
      return false;
    }
  }

  startSession(videoElement) {
    this.resetSession();
    if (!videoElement) {
      this.cameraAvailability = "unavailable";
      return;
    }
    this.cameraAvailability = "available";
    this.isAnalyzing = true;

    this.analysisInterval = setInterval(async () => {
      if (!this.isAnalyzing || !videoElement || videoElement.readyState < 2) return;
      await this._processFrame(videoElement);
    }, CAMERA_CONFIG.sampleIntervalMs);
  }

  stopSession() {
    this.isAnalyzing = false;
    if (this.analysisInterval) {
      clearInterval(this.analysisInterval);
      this.analysisInterval = null;
    }
  }

  resetSession() {
    this.stopSession();
    this.totalFrames = 0;
    this.facePresentFrames = 0;
    this.properFramingFrames = 0;
    this.lookingAwayFrames = 0;
    this.excessiveMovementFrames = 0;
    this.multipleFaceFrames = 0;

    this.lastFaceCenter = null;
    this.movementDeltas = [];
    this.consecutiveLookingAwayCount = 0;

    this.currentFacePresent = false;
    this.currentLookingAway = false;
    this.currentFramingValid = true;
    this.currentPostureStability = 100;
  }

  setPermissionDenied() {
    this.cameraAvailability = "denied";
    this.resetSession();
  }

  async _processFrame(videoElement) {
    try {
      this.totalFrames += 1;
      const options = new faceapi.TinyFaceDetectorOptions({
        inputSize: CAMERA_CONFIG.inputSize,
        scoreThreshold: CAMERA_CONFIG.scoreThreshold,
      });

      // Detect faces in frame
      const detections = await faceapi.detectAllFaces(videoElement, options);

      if (!detections || detections.length === 0) {
        this.currentFacePresent = false;
        this.consecutiveLookingAwayCount = 0;
        return;
      }

      this.facePresentFrames += 1;
      this.currentFacePresent = true;

      // Track multiple faces if observed
      if (detections.length >= CAMERA_CONFIG.multipleFaceThreshold) {
        this.multipleFaceFrames += 1;
      }

      const primaryFace = detections[0];
      const box = primaryFace.box;
      const videoWidth = videoElement.videoWidth || 640;
      const videoHeight = videoElement.videoHeight || 480;

      // 1. Face Centering & Position (Normalized coordinates 0.0 - 1.0)
      const faceCenterX = (box.x + box.width / 2) / videoWidth;
      const faceCenterY = (box.y + box.height / 2) / videoHeight;
      const faceAreaRatio = (box.width * box.height) / (videoWidth * videoHeight);

      // Check Framing Bounds
      const { minX, maxX, minY, maxY } = CAMERA_CONFIG.framingBounds;
      const isCenteredX = faceCenterX >= minX && faceCenterX <= maxX;
      const isCenteredY = faceCenterY >= minY && faceCenterY <= maxY;
      const isProperSize = faceAreaRatio >= CAMERA_CONFIG.faceSizeBounds.minAreaRatio &&
                           faceAreaRatio <= CAMERA_CONFIG.faceSizeBounds.maxAreaRatio;

      const isProperFraming = isCenteredX && isCenteredY && isProperSize;
      if (isProperFraming) {
        this.properFramingFrames += 1;
        this.currentFramingValid = true;
      } else {
        this.currentFramingValid = false;
      }

      // 2. Gaze Alignment / Looking Away Proxy (Centered zone [0.25, 0.75])
      const isGazeCentered = faceCenterX >= 0.25 && faceCenterX <= 0.75 &&
                             faceCenterY >= 0.20 && faceCenterY <= 0.80;

      if (!isGazeCentered) {
        this.consecutiveLookingAwayCount += 1;
      } else {
        this.consecutiveLookingAwayCount = Math.max(0, this.consecutiveLookingAwayCount - 1);
      }

      // Hysteresis: Trigger looking away only after sustained deviation
      if (this.consecutiveLookingAwayCount >= CAMERA_CONFIG.sustainedGazeDeviationFrames) {
        this.lookingAwayFrames += 1;
        this.currentLookingAway = true;
      } else {
        this.currentLookingAway = false;
      }

      // 3. Movement & Posture Stability
      if (this.lastFaceCenter) {
        const dx = faceCenterX - this.lastFaceCenter.x;
        const dy = faceCenterY - this.lastFaceCenter.y;
        const delta = Math.sqrt(dx * dx + dy * dy);
        this.movementDeltas.push(delta);

        if (delta > CAMERA_CONFIG.excessiveMovementThreshold) {
          this.excessiveMovementFrames += 1;
        }
      }
      this.lastFaceCenter = { x: faceCenterX, y: faceCenterY };

    } catch (err) {
      // Non-fatal frame processing error
    }
  }

  /**
   * Computes comprehensive, observable camera delivery metrics for the question session.
   */
  computeMetrics() {
    if (this.cameraAvailability !== "available" || this.totalFrames === 0) {
      return {
        camera_available: false,
        camera_availability: this.cameraAvailability,
        total_frames_analyzed: 0,
        face_presence_pct: 0,
        face_framing_score: 0,
        gaze_stability_score: 0,
        posture_stability_score: 0,
        movement_stability_score: 0,
        camera_observation_coverage: 0,
        multiple_face_events: 0,
        coaching_tips: ["Webcam analytics unavailable (camera offline or permission restricted)."],
      };
    }

    const total = Math.max(1, this.totalFrames);
    const facePresencePct = Math.round((this.facePresentFrames / total) * 100);
    const observationCoverage = facePresencePct;

    // 1. Face Framing Score (0-100)
    const faceFramingScore = this.facePresentFrames > 0
      ? Math.round((this.properFramingFrames / this.facePresentFrames) * 100)
      : 0;

    // 2. Gaze Stability Score (0-100)
    const lookingAwayPct = this.facePresentFrames > 0
      ? Math.round((this.lookingAwayFrames / this.facePresentFrames) * 100)
      : 0;
    const gazeStabilityScore = Math.max(20, Math.min(100, 100 - lookingAwayPct));

    // 3. Posture & Movement Stability Scores (0-100)
    const excessiveMovementRatio = this.facePresentFrames > 0
      ? (this.excessiveMovementFrames / this.facePresentFrames)
      : 0;
    const movementStabilityScore = Math.max(40, Math.min(100, Math.round(100 - (excessiveMovementRatio * 85))));
    const postureStabilityScore = movementStabilityScore;

    // 4. Actionable Observable Coaching Tips (Strictly descriptive, no psychological claims)
    const coachingTips = [];

    if (facePresencePct < 65) {
      coachingTips.push("Face presence was intermittent. Ensure your webcam is positioned directly at eye level with steady lighting.");
    } else {
      coachingTips.push("Consistent camera framing and steady face visibility maintained throughout the answer.");
    }

    if (lookingAwayPct > 35) {
      coachingTips.push("Observable gaze deviation was detected during portions of the response. Aiming your gaze toward the upper screen or camera simulates natural interview eye contact.");
    } else if (facePresencePct >= 65 && lookingAwayPct <= 15) {
      coachingTips.push("Excellent gaze alignment maintained facing the interviewer.");
    }

    if (movementStabilityScore < 70) {
      coachingTips.push("Frequent head or upper-body displacement was detected. Maintaining a grounded, steady posture supports clear delivery.");
    } else {
      coachingTips.push("Good posture stability and steady physical presence observed.");
    }

    if (this.multipleFaceFrames > 5) {
      coachingTips.push("Multiple individuals were detected in camera frame during the answer. For best interview simulation, ensure an isolated setting.");
    }

    return {
      camera_available: true,
      camera_availability: "available",
      total_frames_analyzed: this.totalFrames,
      face_presence_pct: facePresencePct,
      face_framing_score: faceFramingScore,
      gaze_stability_score: gazeStabilityScore,
      looking_away_pct: lookingAwayPct,
      posture_stability_score: postureStabilityScore,
      movement_stability_score: movementStabilityScore,
      camera_observation_coverage: observationCoverage,
      multiple_face_events: this.multipleFaceFrames,
      coaching_tips: coachingTips,
    };
  }

  getSummary() {
    return this.computeMetrics();
  }
}

export const defaultCameraEngine = new CameraAnalyticsEngine();
