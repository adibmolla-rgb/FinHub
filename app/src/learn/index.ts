import { career } from './curriculum/career'
import { coding } from './curriculum/coding'
import { markets } from './curriculum/markets'
import { maths } from './curriculum/maths'
import { methods } from './curriculum/methods'
import { start } from './curriculum/start'
import type { Lesson, Track } from './types'

// Tracks in teaching order. To add a course, write a Track (see types.ts) in curriculum/ and list it here.
// Set access: 'premium' to mark it as paid content; access control is not implemented yet (see Learn.tsx).
export const TRACKS: Track[] = [start, markets, maths, coding, methods, career]

export const ALL_LESSONS: { track: Track; lesson: Lesson }[] = TRACKS.flatMap((track) => track.lessons.map((lesson) => ({ track, lesson })))

export function findLesson(id: string) {
  return ALL_LESSONS.find((x) => x.lesson.id === id)
}
