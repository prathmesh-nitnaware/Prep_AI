import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import {
  Mic,
  MicOff,
  ChevronRight,
  Loader2,
  Activity,
  Video,
  VideoOff,
  Volume2,
  CheckCircle2,
  Clock,
  Send,
  Layers,
  Sparkles,
} from 'lucide-react';
import { defaultVoiceEngine } from '../utils/voiceAnalytics';
import { defaultCameraEngine } from '../utils/cameraAnalytics';
import './InterviewLive.css';

const STAGES = [
  { id: 1, name: 'Fundamentals' },
  { id: 2, name: 'Applied Scenarios' },
  { id: 3, name: 'Deep Technical Probing' },
  { id: 4, name: 'System Architecture' },
  { id: 5, name: 'Behavioral STAR' },
];

const InterviewLive = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const sessionId = location.state?.session_id;
  const config = location.state?.config || { role: 'Software Engineer', intensity: 5 };
  const MAX_QUESTIONS = parseInt(config.intensity) || 5;

  const initialQuestion = location.state?.question || {
    id: 1,
    title: 'Question 1',
    description: 'Preparing your first interview question...',
    question: 'Preparing your first interview question...',
  };

  const [question, setQuestion] = useState(initialQuestion);
  const [sessionHistory, setSessionHistory] = useState([]);
  const [questionIndex, setQuestionIndex] = useState(1);
  const [userAnswer, setUserAnswer] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [loadingNext, setLoadingNext] = useState(false);
  const [isAiSpeaking, setIsAiSpeaking] = useState(false);

  // Behavioral Telemetry
  const [cameraActive, setCameraActive] = useState(true);
  const [faceDetected, setFaceDetected] = useState(true);
  const [liveWpm, setLiveWpm] = useState(0);
  const [liveFillers, setLiveFillers] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const recognitionRef = useRef(null);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const recordedChunksRef = useRef([]);

  // Timer interval while answering
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!sessionId) {
      navigate('/interview');
      return;
    }
    setupSpeechRecognition();
    initHardwareAndAnalytics();

    const qText = question.question || question.description || question.title;
    if (qText) speakText(qText);

    return () => {
      window.speechSynthesis.cancel();
      defaultVoiceEngine.cleanup();
      defaultCameraEngine.stopSession();
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        try { mediaRecorderRef.current.stop(); } catch(e){}
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
    };
  }, []);

  const initHardwareAndAnalytics = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: true,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setCameraActive(true);

      // Start video/audio recording
      try {
        const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9')
          ? 'video/webm;codecs=vp9'
          : 'video/webm';
        const recorder = new MediaRecorder(stream, { mimeType });
        recordedChunksRef.current = [];
        recorder.ondataavailable = (event) => {
          if (event.data && event.data.size > 0) {
            recordedChunksRef.current.push(event.data);
          }
        };
        recorder.start(1000);
        mediaRecorderRef.current = recorder;
      } catch (recErr) {
        console.warn('MediaRecorder initialization warning:', recErr);
      }

      await defaultVoiceEngine.initializeAudioMonitoring(stream);
      await defaultCameraEngine.loadModels('/models');
      if (videoRef.current) {
        defaultCameraEngine.startSession(videoRef.current);
      }
    } catch (e) {
      setCameraActive(false);
    }
  };

  const finishAndProcessRecording = async () => {
    return new Promise((resolve) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state === 'inactive') {
        resolve(null);
        return;
      }

      recorder.onstop = async () => {
        try {
          const blob = new Blob(recordedChunksRef.current, { type: 'video/webm' });

          // 1. AUTO DOWNLOAD TO CANDIDATE'S PC
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.style.display = 'none';
          a.href = url;
          a.download = `PrepAI_Interview_${sessionId || 'Session'}.webm`;
          document.body.appendChild(a);
          a.click();
          setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
          }, 1000);

          // 2. UPLOAD TO BACKEND DATABASE / STORAGE
          if (sessionId) {
            await api.uploadInterviewRecording(sessionId, blob);
          }
          resolve(blob);
        } catch (err) {
          console.error('Error saving/downloading recording:', err);
          resolve(null);
        }
      };

      try {
        recorder.stop();
      } catch (err) {
        resolve(null);
      }
    });
  };

  useEffect(() => {
    const hudInterval = setInterval(() => {
      setFaceDetected(defaultCameraEngine.currentFacePresent);

      if (isListening && userAnswer.trim().length > 0) {
        const metrics = defaultVoiceEngine.computeMetrics(userAnswer);
        setLiveWpm(metrics.wpm);
        setLiveFillers(metrics.filler_word_count);
      }
    }, 500);

    return () => clearInterval(hudInterval);
  }, [isListening, userAnswer]);

  const setupSpeechRecognition = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;
    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0].transcript)
        .join('');
      setUserAnswer(transcript);
    };
    recognitionRef.current = recognition;
  };

  const speakText = (text) => {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    utterance.onstart = () => setIsAiSpeaking(true);
    utterance.onend = () => setIsAiSpeaking(false);
    utterance.onerror = () => setIsAiSpeaking(false);

    window.speechSynthesis.speak(utterance);
  };

  const toggleListening = () => {
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
    } else {
      window.speechSynthesis.cancel();
      setIsAiSpeaking(false);
      try {
        recognitionRef.current?.start();
        setIsListening(true);
      } catch (err) {
        setIsListening(false);
      }
    }
  };

  const handleSubmitAnswer = async () => {
    if (isListening) toggleListening();

    const finalAnswer = userAnswer.trim() || 'No answer provided.';
    setSubmitting(true);
    setLoadingNext(true);

    let voiceMetrics = {};
    let cameraMetrics = {};
    try {
      if (typeof defaultVoiceEngine?.computeMetrics === 'function') {
        voiceMetrics = defaultVoiceEngine.computeMetrics(finalAnswer);
      }
    } catch (e) {
      console.warn('Voice metrics computation error:', e);
    }
    try {
      if (typeof defaultCameraEngine?.computeMetrics === 'function') {
        cameraMetrics = defaultCameraEngine.computeMetrics();
      } else if (typeof defaultCameraEngine?.getSummary === 'function') {
        cameraMetrics = defaultCameraEngine.getSummary();
      }
    } catch (e) {
      console.warn('Camera metrics computation error:', e);
    }

    const payload = {
      session_id: sessionId,
      question_id: question.id || questionIndex,
      question: question.question || question.description || question.title,
      answer: finalAnswer,
      voice_metrics: voiceMetrics,
      camera_metrics: cameraMetrics,
      context: {
        role: config.role,
        question_index: questionIndex,
      },
    };

    try {
      if (questionIndex >= MAX_QUESTIONS) {
        // Last question: finish evaluation, save & download recording, then navigate to final report
        const evalResponse = await api.submitAnswer(payload);
        const updatedHistory = [
          ...sessionHistory,
          {
            question: question.question || question.description || question.title,
            answer: finalAnswer,
            feedback: evalResponse?.feedback || evalResponse,
            voice_metrics: voiceMetrics,
            camera_metrics: cameraMetrics,
          },
        ];
        setSessionHistory(updatedHistory);
        await finishAndProcessRecording();
        navigate('/interview/report', {
          state: {
            history: updatedHistory,
            config: config,
            session_id: sessionId,
          },
        });
        return;
      }

      // Execute answer evaluation and fetching next question in parallel
      const [evalResult, nextResult] = await Promise.allSettled([
        api.submitAnswer(payload),
        api.getNextQuestion({
          session_id: sessionId,
          current_index: questionIndex - 1,
          current_question_index: questionIndex - 1,
          previous_answer: finalAnswer,
        }),
      ]);

      let evalFeedback = {};
      if (evalResult.status === 'fulfilled') {
        evalFeedback = evalResult.value?.feedback || evalResult.value || {};
      } else {
        console.warn('Background evaluation warning:', evalResult.reason);
      }

      const updatedHistory = [
        ...sessionHistory,
        {
          question: question.question || question.description || question.title,
          answer: finalAnswer,
          feedback: evalFeedback,
          voice_metrics: voiceMetrics,
          camera_metrics: cameraMetrics,
        },
      ];
      setSessionHistory(updatedHistory);

      let nextQ = null;
      if (nextResult.status === 'fulfilled' && nextResult.value) {
        nextQ = nextResult.value.question || nextResult.value.data?.question;
      }

      if (nextQ) {
        setQuestion(nextQ);
        setQuestionIndex((prev) => prev + 1);
        setUserAnswer('');
        const qText = nextQ.question || nextQ.description || nextQ.title;
        if (qText) speakText(qText);
      } else {
        // If index target reached or completed
        await finishAndProcessRecording();
        navigate('/interview/report', {
          state: {
            history: updatedHistory,
            config: config,
            session_id: sessionId,
          },
        });
      }
    } catch (err) {
      console.error('Answer submission error:', err);
    } finally {
      setSubmitting(false);
      setLoadingNext(false);
    }
  };

  const handleSkip = () => {
    if (window.confirm('Skip this question and proceed to the next stage?')) {
      setUserAnswer('Skipped');
      setTimeout(() => handleSubmitAnswer(), 50);
    }
  };

  const formatTimer = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const currentStageName = STAGES[Math.min(questionIndex - 1, STAGES.length - 1)].name;

  return (
    <div className="interview-studio-page">
      <div className="studio-container">
        {/* Studio Top Bar */}
        <div className="studio-top-bar">
          <div className="studio-meta-group">
            <span className="studio-brand-tag">PREP AI</span>
            <span className="studio-role-title">{config.role}</span>
            <span className="studio-stage-pill">
              Stage {questionIndex} / {MAX_QUESTIONS}: {currentStageName}
            </span>
          </div>

          <div className="studio-timer-box">
            <Clock size={14} />
            <span>{formatTimer(elapsedSeconds)}</span>
          </div>
        </div>

        {/* Main 2-Column Grid */}
        <div className="studio-main-grid">
          {/* Left: Question Prompt & Answer Workspace */}
          <div className="studio-workspace-col">
            {/* Interviewer Question Card */}
            <div className="interviewer-question-card">
              <div className="question-header-row">
                <span className="question-stage-label">Interviewer Question #{questionIndex}</span>
                {isAiSpeaking && (
                  <span className="speaker-indicator-badge">
                    <Volume2 size={13} /> Speaking...
                  </span>
                )}
              </div>

              <h2 className="question-text-content">
                {question.question || question.description || question.title}
              </h2>

              {question.intent && (
                <div className="question-intent-meta">
                  Intent: {question.intent}
                </div>
              )}
            </div>

            {/* Candidate Response Workspace */}
            <div className="candidate-response-card">
              <div className="response-card-header">
                <span className="response-label">Your Verbal / Written Response</span>
                {isListening && (
                  <div className="listening-pulse-indicator">
                    <div className="recording-dot"></div>
                    <span>Listening to microphone...</span>
                  </div>
                )}
              </div>

              <textarea
                className="candidate-answer-textarea"
                placeholder="Speak clearly or type your structured response here..."
                value={userAnswer}
                onChange={(e) => setUserAnswer(e.target.value)}
                disabled={submitting || loadingNext}
              />

              <div className="response-actions-toolbar">
                <button
                  type="button"
                  className={`mic-toggle-control ${isListening ? 'active' : ''}`}
                  onClick={toggleListening}
                  disabled={submitting || loadingNext}
                >
                  {isListening ? <MicOff size={15} /> : <Mic size={15} />}
                  <span>{isListening ? 'Stop Recording' : 'Voice Input'}</span>
                </button>

                <div className="submission-actions-group">
                  <button
                    type="button"
                    className="btn-skip-question"
                    onClick={handleSkip}
                    disabled={submitting || loadingNext}
                  >
                    Skip
                  </button>

                  <button
                    type="button"
                    className="btn-submit-answer"
                    onClick={handleSubmitAnswer}
                    disabled={submitting || loadingNext || (!userAnswer.trim() && !isListening)}
                  >
                    {submitting ? (
                      <>
                        <Loader2 size={14} className="spin" /> Evaluating...
                      </>
                    ) : loadingNext ? (
                      <>
                        <Loader2 size={14} className="spin" /> Next Question...
                      </>
                    ) : (
                      <>
                        <span>Submit Answer</span>
                        <Send size={13} />
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Right: Camera Feed, Telemetry, and Stage Tracker */}
          <div className="studio-sidebar-col">
            {/* Small Camera Preview Box */}
            <div className="studio-camera-card">
              <div className="camera-header-status">
                <span>SIGNAL FEED</span>
                <span style={{ color: cameraActive ? '#34d399' : '#8c8ca0' }}>
                  {cameraActive ? '● Camera Active' : '○ Offline'}
                </span>
              </div>
              <div className="camera-feed-container">
                {cameraActive ? (
                  <video ref={videoRef} autoPlay playsInline muted className="studio-video-element" />
                ) : (
                  <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6a6a7c', fontSize: '0.8rem' }}>
                    Camera Offline (Typed Mode)
                  </div>
                )}
              </div>
            </div>

            {/* Live Delivery Telemetry */}
            <div className="studio-telemetry-panel">
              <h3 className="telemetry-heading">Live Telemetry</h3>
              <div className="telemetry-metrics-grid">
                <div className="metric-tile">
                  <span className="metric-val">{liveWpm}</span>
                  <span className="metric-lbl">Words / Min</span>
                </div>
                <div className="metric-tile">
                  <span className="metric-val">{liveFillers}</span>
                  <span className="metric-lbl">Fillers Count</span>
                </div>
              </div>
            </div>

            {/* 5-Stage Progression Tracker */}
            <div className="studio-stage-tracker">
              <h3 className="telemetry-heading">Interview Stages</h3>
              {STAGES.map((s) => {
                const isCurrent = s.id === questionIndex;
                const isDone = s.id < questionIndex;
                return (
                  <div
                    key={s.id}
                    className={`stage-tracker-item ${isCurrent ? 'active' : isDone ? 'completed' : ''}`}
                  >
                    <div className="stage-dot"></div>
                    <span>
                      {s.id}. {s.name}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default InterviewLive;
