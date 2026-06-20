# Ripple User Profile Roadmap

This document outlines the features and progression strategy for the User Profile section in Ripple. The implementation is broken down into clear phases starting from the MVP up to advanced AI diagnostics and social capabilities.

---

## 🚀 Phase 1: MVP (Minimum Viable Product)
*Focus: Basic identity, session history, and essential configuration.*

### 1. User Identity & Settings
*   **Basic Profile Card**: Displays user avatar, name, and email (loaded via Google Sign-In).
*   **Role & Background Context**: Simple input fields for the user's role (e.g., *"Product Manager"*, *"College Student"*) and a short bio. This context is injected into non-challenge custom conversations to personalize responses.
*   **Active Settings**: Basic toggle switches for sound effects, haptics, and interface preferences.

### 2. Basic Attempt Summary
*   **Summary Counters**: Clean counters displaying:
    *   Total challenges attempted.
    *   Success rate percentage (won vs. lost).
    *   Total practice sessions.
*   **Attempt Log**: A scrollable history list showing recent challenge runs with the challenge title, date, target persona, and result badge (Success/Failure).

---

## 🎮 Phase 2: Gamification & Stats Tracking
*Focus: Encouraging daily practice and tracking core conversational skills.*

### 1. XP & Leveling System
*   **Experience Points (XP)**: Earn XP for taking turns, successfully completing challenges, and attempting higher difficulties.
*   **Animated Level Ring**: A premium, glassmorphic progress circle showing current level title (e.g., *Level 5: Negotiator-in-Training*) and XP needed to rank up.
*   **Daily Streaks Grid**: A GitHub-style contribution grid visualization displaying daily active practice sessions to drive retention.

### 2. Conversational Skill Radars
*   **Core Skill Ratings**: 0-100% scores across major conversational pillars evaluated by Gemini during runs:
    *   **Negotiation**: Handling trade-offs, value creation, and pricing.
    *   **Empathy**: Validating emotions and listening actively.
    *   **Wit/Banter**: Responding quickly with humor or sarcasm.
    *   **De-escalation**: Defusing defensive or angry personas.
*   **Skill Radar Chart**: Visual representation of the above scores to help users quickly identify their strengths.

---

## 🧠 Phase 3: The "AI Mirror" & Personalization
*Focus: Deep AI diagnostics on user behavior and advanced context tailoring.*

### 1. AI-Compiled Speech Profile
*   **Speech Style tags**: Machine-learned tags based on historical message analysis (e.g., *Direct*, *Empathetic*, *Formal*, *Verbally Assertive*).
*   **AI Mirror Cards**: "How Personas See You" panel listing:
    *   *Warmth Rating*: 0-10 metric based on conversational friendliness.
    *   *Assertiveness*: 0-10 metric based on boundary setting.
    *   *Vulnerability*: 0-10 metric based on openness.
*   **AI Coach Feedback**: A dynamic text area showing constructive advice compiled from recent chat attempts (e.g., *"You successfully hold boundaries, but try asking more open-ended questions to build rapport early."*).

### 2. Advanced Learning Goals
*   **Practice Focus settings**: Dropdown to select current learning focus (e.g., *Assertiveness*, *Active Listening*, *Salary negotiation*).
*   **Context Injector**: Feeds the selected goal into custom chats to guide the persona's AI behaviors towards testing those specific skills.

---

## 🌐 Phase 4: Social, Replays & Advanced Metrics
*Focus: Benchmarking against others and reviewing transcripts.*

### 1. Interactive Chat Replays
*   **Transcript Repository**: Click on any past attempt in the profile log to open a modal displaying the exact transcript of that conversation.
*   **Shareable Transcripts**: Generate private link tokens or formatted screenshots to share attempts with friends or mentors for review.
*   **Replay with AI Hints**: Reviewing a past attempt shows alternative response suggestions that could have led to a better score.

### 2. Community & Benchmarks
*   **Global Skill Benchmarks**: Compare your Radar Chart averages with global user averages in your profession (e.g., *"Your Negotiation skill is in the top 15% of Sales Managers"*).
*   **Leaderboards**: Weekly challenges showing who won advanced scenarios with the fewest turns or highest final trust scores.
*   **Trophy Case**: Display of earned badges/achievements (e.g., *Sarcasm Survivor*, *The Closer*, *Crisis Handler*).
