/** The name the home page's ask box and the agent page's composer both claim.
 *
 *  A `view-transition-name` is what turns a route change into a movement: the
 *  browser matches the old and new elements carrying the same name and
 *  interpolates position, size and radius between them, so the box the reader
 *  typed into travels to where the composer sits instead of vanishing and a
 *  differently-shaped control appearing elsewhere.
 *
 *  Shared through a constant rather than typed twice because the whole effect
 *  is silent if the two spellings drift: nothing errors, the pages just cut.
 *
 *  It must be unique per document — only one element may carry it at a time,
 *  which holds here because the two pages are never mounted together. */
export const ASK_BOX_TRANSITION_NAME = "ask-box";
