"use client";
import Image from "next/image";
import { useState } from 'react';

type Source = {
  id: string;
  text: string;
  metadata: {
    chapter_title?: string;
    section_title?: string;
    page?: number;
  };
};

type AskResponse = {
  question: string;
  answer: string;
  sources: Source[];
};

export default function Home() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
  setLoading(true);
  try {
    const res = await fetch("http://localhost:8000/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!res.ok) throw new Error(`API returned ${res.status}`);
    const data = await res.json();
    setResult(data);
  } catch (err) {
    setError(err instanceof Error ? err.message : "Something went wrong");
  } finally {
    setLoading(false);
  }
};

  return (
    <div style={{ padding: '20px', fontFamily: 'sans-serif' }}>
      <h1>Ask a Question</h1>
      <input
        type="text"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Type your question here..."
        style={{ width: '300px', padding: '10px', marginRight: '10px' }}
      />

      <div style={{ marginTop: '20px' }}>
        {loading && <p>Loading...</p>}
        {!loading && result && (
          <>
            <p>{result.answer}</p>
            <h3>Sources</h3>
            {result.sources.map((s) => (
              <div key={s.id} style={{ marginBottom: '12px', fontSize: '0.9em' }}>
                <strong>
                  {s.metadata.chapter_title} — {s.metadata.section_title} (p. {s.metadata.page})
                </strong>
                <p>{s.text}</p>
              </div>
            ))}
          </>
        )}
      </div>
      
      <button onClick={handleSubmit}>
        Click me
      </button>
    </div>
  );
}
