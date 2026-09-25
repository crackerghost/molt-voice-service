import { Component } from "react";

/* Per-window crash containment: one app's render fault (e.g. an editor DOM
   collision) shows a fallback card inside THAT window instead of unmounting
   the whole desktop. Voice, board, and every other window keep running.
   The boundary unmounts with its window, so reopening starts clean. */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    try {
      // eslint-disable-next-line no-console
      console.error(`[${this.props.appName || "app"}] crashed:`, error, info?.componentStack);
    } catch { /* logging must never throw */ }
  }

  render() {
    if (!this.state.error) return this.props.children;
    const { appName } = this.props;
    return (
      <div className="flex h-full min-h-0 flex-col items-center justify-center gap-2 bg-[#1e1e1e] p-6 text-center">
        <p className="text-sm font-bold text-white">{appName || "App"} ran into a problem</p>
        <p className="max-w-sm text-xs leading-5 text-gray-400">
          This window crashed, but the rest of the desktop — including voice — is still running.
        </p>
        <button
          onClick={() => this.setState({ error: null })}
          className="mt-1 rounded-full bg-[#0e639c] px-4 py-1.5 text-xs font-bold text-white transition hover:bg-[#1177bb]"
        >
          Try again
        </button>
      </div>
    );
  }
}
