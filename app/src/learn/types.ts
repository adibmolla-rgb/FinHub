// Course content model. Lessons are written in a small Markdown subset (see markdown.tsx).

export type QuizQuestion = {
  q: string
  options: string[]
  answer: number // index into options
  why: string // shown after answering, right or wrong
}

export type Resource = { title: string; url: string; note?: string; free?: boolean }

export type Lesson = {
  id: string // unique across all tracks, e.g. "maths-probability"
  title: string
  minutes: number // reading + exercises, roughly
  summary: string // one line, shown in the lesson list
  body: string // Markdown subset
  quiz?: QuizQuestion[]
  tryIt?: { command: string; label: string }[] // runs a FinHub command
  resources?: Resource[]
}

export type Track = {
  id: string
  title: string
  description: string
  // Every track is free today. "premium" is reserved for future paid courses; the UI already
  // labels them, and access control would be added where marked in Learn.tsx.
  access: 'free' | 'premium'
  lessons: Lesson[]
}
