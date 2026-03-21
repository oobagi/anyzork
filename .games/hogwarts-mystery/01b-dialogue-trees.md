# Hogwarts Mystery — Dialogue Trees

All dialogue written in ZorkScript `talk` node format.
Flag and item references align with the game design document.

---

## 1. Professor McGonagall — Great Hall

```zorkscript
// ============================================================
// McGONAGALL — great_hall
// Pre-quest: concern about the castle, points player to Dumbledore
// Post-quest: encouragement and guidance
// ============================================================

talk mcgonagall_greeting {
  "Potter. I trust you haven't been wandering unsupervised. The castle is...
   not itself tonight."
  option "What's happening, Professor?" -> mcgonagall_concern
  option "I need to see Dumbledore." -> mcgonagall_dumbledore
  option "I can handle myself." -> mcgonagall_dismissive
}

talk mcgonagall_concern {
  "The wards are failing. Doors that have been sealed for centuries are
   opening on their own. Staircases are refusing to move — or moving too
   much. I have never seen anything like it in all my years here."
  option "Do you know what's causing it?" -> mcgonagall_cause
  option "How can I help?" -> mcgonagall_help
  option "I need to see Dumbledore." -> mcgonagall_dumbledore
}

talk mcgonagall_cause {
  "The Headmaster believes it is connected to something ancient. Something
   buried in the foundations of this school long before any of us arrived.
   You should speak with him directly."
  option "Where is Dumbledore?" -> mcgonagall_dumbledore
  option "Thank you, Professor." -> mcgonagall_farewell
}

talk mcgonagall_help {
  "You can help by being careful, Potter. This is not a matter of courage.
   It is a matter of not getting yourself killed before you can be useful."
  option "I need to see Dumbledore." -> mcgonagall_dumbledore
  option "I'll be careful." -> mcgonagall_farewell
}

talk mcgonagall_dismissive {
  "That is precisely the attitude that fills beds in the hospital wing.
   Listen to me. Whatever bravado carried you through previous years will
   not be sufficient tonight."
  option "You're right. What should I do?" -> mcgonagall_help
  option "Where's Dumbledore?" -> mcgonagall_dumbledore
}

talk mcgonagall_dumbledore {
  "The Headmaster is in his office. The gargoyle on the second floor
   corridor — you know the one."
  option "What's the password?" -> mcgonagall_password
  option "I know the way. Thank you." -> mcgonagall_farewell
}

talk mcgonagall_password {
  "Sherbet Lemon. The man's sweet tooth will be the death of his security.
   Do not repeat that to anyone, Potter."
  sets [knows_gargoyle_password]
  option "Thank you, Professor." -> mcgonagall_farewell
}

talk mcgonagall_farewell {
  "Go. And Potter — keep your wand ready."
}

// --- Post-quest dialogue (after has_main_quest) ---

talk mcgonagall_postquest {
  required_flags [has_main_quest]
  "You've spoken with the Headmaster, then. I can see it in your face.
   The weight of it."
  option "He's asking a lot." -> mcgonagall_encourage
  option "I'll manage." -> mcgonagall_encourage_brief
  option "Do you know about Malachar?" -> mcgonagall_malachar
}

talk mcgonagall_encourage {
  "He asks because he trusts you. That is not a small thing. Albus
   Dumbledore does not place trust carelessly."
  option "What if I'm not enough?" -> mcgonagall_enough
  option "Thank you, Professor." -> mcgonagall_postquest_farewell
}

talk mcgonagall_encourage_brief {
  "I have no doubt. But managing and succeeding are different creatures.
   Do not confuse stubbornness for strategy."
  option "I won't." -> mcgonagall_postquest_farewell
}

talk mcgonagall_malachar {
  "I know what the staff has been told. An ancient threat. A wizard who
   tried to bind the Founders' magic into a single artifact. Beyond that,
   the Headmaster has kept his own counsel."
  option "He seems worried." -> mcgonagall_enough
  option "Thank you." -> mcgonagall_postquest_farewell
}

talk mcgonagall_enough {
  "You are not doing this alone. Remember that. The castle itself is on
   your side, Potter — even when it doesn't look like it."
  option "That's... actually reassuring." -> mcgonagall_postquest_farewell
  option "I hope you're right." -> mcgonagall_postquest_farewell
}

talk mcgonagall_postquest_farewell {
  "Now stop dawdling. You have trials to face, and they will not wait
   for sentimentality."
}
```

---

## 2. Albus Dumbledore — Dumbledore's Office (CRITICAL)

```zorkscript
// ============================================================
// DUMBLEDORE — dumbledore_office
// The primary quest-giver. Mission briefing, item distribution,
// lore exposition through Socratic questioning.
// ============================================================

talk dumbledore_greeting {
  "Ah, Harry. I wondered when you would arrive. Please — sit. There are
   Lemon Drops on the desk if you'd like one. I find sugar helps with
   difficult conversations."
  option "What's happening to the castle?" -> dumbledore_castle
  option "McGonagall sent me." -> dumbledore_mcgonagall
  option "No small talk, Professor. Tell me what's wrong." -> dumbledore_direct
}

talk dumbledore_castle {
  "A fair question, and one I owe you an honest answer to. The castle is
   waking up — or rather, something beneath it is. Something that has been
   sleeping since the Founders walked these halls."
  option "What is it?" -> dumbledore_stone_intro
  option "The Founders? This goes back that far?" -> dumbledore_founders
}

talk dumbledore_mcgonagall {
  "Minerva is efficient as always. She would have told you the castle is
   in distress. She is correct, though 'distress' understates the matter
   considerably."
  option "How bad is it?" -> dumbledore_stone_intro
  option "She seemed frightened." -> dumbledore_minerva_fear
}

talk dumbledore_minerva_fear {
  "Minerva does not frighten easily. When she does, I pay attention. You
   should as well."
  option "Tell me everything." -> dumbledore_stone_intro
}

talk dumbledore_direct {
  "Very well. I have always appreciated your directness, Harry, even when
   it borders on impatience."
  option "..." -> dumbledore_stone_intro
}

talk dumbledore_founders {
  "Further, in fact. The roots of this reach back to a time when the four
   Founders were not yet legends — when they were merely brilliant,
   frightened people trying to build something that would outlast them."
  option "Go on." -> dumbledore_stone_intro
}

talk dumbledore_stone_intro {
  "There is an artifact hidden in the deepest foundations of this school.
   It is called the Convergence Stone. The Founders created it together —
   a single object that channels all four of their magical traditions into
   one. It was meant to be the heart of Hogwarts. Its power source. Its
   soul, if you will."
  sets [knows_stone_lore]
  option "Why haven't I heard of this before?" -> dumbledore_secrecy
  option "What went wrong?" -> dumbledore_malachar_intro
  option "And now it's causing all this?" -> dumbledore_malachar_intro
}

talk dumbledore_secrecy {
  "Because some truths are too dangerous for textbooks. The Stone's
   existence was known only to the Headmasters of Hogwarts, passed down
   in whispers. I am the latest in a long line of keepers — and I fear
   I may be the last, if we do not act."
  option "What went wrong with it?" -> dumbledore_malachar_intro
}

talk dumbledore_malachar_intro {
  "A wizard named Malachar. He was a student here, centuries ago. Brilliant.
   Perhaps the most gifted student this school has ever produced — and I do
   not say that lightly. He discovered the Stone's existence, and he became
   obsessed with it. He believed he could use it to unify all magic under
   a single will. His will."
  option "What happened to him?" -> dumbledore_malachar_fate
  option "How is he connected to what's happening now?" -> dumbledore_curse
}

talk dumbledore_malachar_fate {
  "The Founders stopped him. Together, they bound him — not killed, mind
   you, but trapped. Sealed within the Stone's own chamber, his curse
   woven into the fabric of the school itself. For centuries, the binding
   held. It is not holding any longer."
  option "The curse is breaking free." -> dumbledore_curse
}

talk dumbledore_curse {
  "Malachar placed a curse on the Stone before he was bound. A slow,
   patient thing. It has been eroding the Founders' protections for a
   thousand years, and now the walls are thin. The disturbances you see —
   the shifting corridors, the failing wards — those are symptoms. The
   disease is far worse."
  option "What do we need to do?" -> dumbledore_trials
  option "Can't you stop it?" -> dumbledore_why_harry
}

talk dumbledore_why_harry {
  "I have tried. The curse is designed to resist any single magical
   tradition. It requires something I cannot provide: a wizard who can
   earn the trust of all four Founders' legacies. Their trials were built
   for a student, Harry. Not a Headmaster."
  option "Trials?" -> dumbledore_trials
}

talk dumbledore_trials {
  "The Founders foresaw that the Stone might one day need a champion. They
   each created a trial — a test of the virtue they valued most. Courage
   for Gryffindor. Wisdom for Ravenclaw. Loyalty for Hufflepuff. Cunning
   for Slytherin. A wizard who passes all four trials can reach the Stone
   and restore the binding."
  option "And you want me to do this." -> dumbledore_assignment
  option "All four? Even Slytherin?" -> dumbledore_slytherin
}

talk dumbledore_slytherin {
  "Even Slytherin. Cunning is not cruelty, Harry. Salazar Slytherin valued
   resourcefulness, self-preservation, and the willingness to make
   difficult choices. These are not evil qualities — merely dangerous ones,
   when misused."
  option "I understand." -> dumbledore_assignment
  option "I'm not sure I can think like a Slytherin." -> dumbledore_reassure
}

talk dumbledore_reassure {
  "The Sorting Hat considered placing you in Slytherin, as I recall. You
   have more of Salazar's qualities than you credit yourself with. That
   is not a failing."
  option "Fine. What do I need?" -> dumbledore_assignment
}

talk dumbledore_assignment {
  "I will not send you into this unprepared. I have three things for you."
  option "I'm listening." -> dumbledore_items
}

talk dumbledore_items {
  "First — this lantern. It is enchanted to reveal hidden passages and
   dispel minor illusions. The trials are concealed within the school, and
   you will need it to find them."
  // Item given: enchanted_lantern
  option "Thank you. What else?" -> dumbledore_items_2
}

talk dumbledore_items_2 {
  "Second — a permission slip for the Restricted Section of the library.
   Miss Granger will be invaluable to you, and she will need access to
   texts that are otherwise sealed. Give this to her when the time comes."
  // Item given: permission_slip
  option "And the third?" -> dumbledore_items_3
}

talk dumbledore_items_3 {
  "Your father's Invisibility Cloak. I have been holding it for precisely
   this kind of occasion. There will be places in the trials where stealth
   serves better than strength."
  // Item given: invisibility_cloak
  option "My dad's cloak..." -> dumbledore_cloak_emotion
  option "I'll put it to good use." -> dumbledore_sendoff
}

talk dumbledore_cloak_emotion {
  "He would be proud of you tonight, Harry. Both of them would."
  option "..." -> dumbledore_sendoff
}

talk dumbledore_sendoff {
  "One more thing. You will not be able to do this alone. The Founders
   designed their trials to test more than one person — to test bonds.
   Trust your friends. Let them help you. That is not weakness. It is the
   very thing Malachar could never understand."
  sets [has_main_quest]
  option "I won't let you down." -> dumbledore_final
  option "What if I fail?" -> dumbledore_fail
}

talk dumbledore_fail {
  "Then the binding breaks. Malachar's curse consumes the Stone. And
   Hogwarts — the real Hogwarts, the idea of it, not merely the building —
   ceases to exist. But I do not believe you will fail, Harry. I never
   have."
  option "Then I'd better get started." -> dumbledore_final
}

talk dumbledore_final {
  "Off you go, then. And Harry — the Lemon Drop offer stands. For when
   you return."
}

// --- Later dialogue: after at least one trial completed ---

talk dumbledore_progress {
  required_flags [has_main_quest]
  "You've returned. I can feel the shift in the castle — something is
   responding to your progress. Tell me what you have learned."
  option "The trials are harder than I expected." -> dumbledore_trials_hard
  option "Tell me more about Malachar." -> dumbledore_malachar_deep
  option "I found something strange in the trials." -> dumbledore_strange
}

talk dumbledore_trials_hard {
  "They were not designed to be completed easily. They were designed to be
   completed honestly. There is a difference."
  option "What do you mean?" -> dumbledore_honesty
  option "Tell me about Malachar." -> dumbledore_malachar_deep
}

talk dumbledore_honesty {
  "The trials test virtue, not skill. You cannot brute-force courage, or
   trick your way through loyalty. You must mean it. The magic knows."
  option "Tell me more about Malachar." -> dumbledore_malachar_deep
  option "I'll keep that in mind." -> dumbledore_progress_farewell
}

talk dumbledore_malachar_deep {
  "Malachar was not born a villain, Harry. He was born a half-blood in an
   era that despised them. He came to Hogwarts seeking belonging, and what
   he found was four contradictory philosophies that could not agree on
   what magic was for. He decided to end the argument. Permanently."
  sets [dumbledore_malachar_info]
  option "He wanted to unify the houses?" -> dumbledore_malachar_unity
  option "That almost sounds sympathetic." -> dumbledore_malachar_sympathy
}

talk dumbledore_malachar_unity {
  "He wanted to erase them. Unification, to Malachar, meant domination.
   One tradition. One purpose. One will governing all of magic. He could
   not tolerate disagreement — and that is what destroyed him. The
   Founders' greatest strength was that they argued. That they were
   different. Malachar saw diversity as weakness. He was wrong."
  option "And the curse?" -> dumbledore_malachar_curse_detail
  option "Thank you, Professor." -> dumbledore_progress_farewell
}

talk dumbledore_malachar_sympathy {
  "It should. The most dangerous people are those whose cause begins with
   a legitimate grievance. Malachar suffered real injustice. His response
   to that injustice is what made him a monster — not his pain."
  option "What exactly does his curse do?" -> dumbledore_malachar_curse_detail
  option "I understand." -> dumbledore_progress_farewell
}

talk dumbledore_malachar_curse_detail {
  "It feeds on division. Every argument between students, every rivalry
   between houses, every moment of distrust — the curse draws strength
   from it. That is why the trials require unity. That is why you need
   allies from every house, every temperament. Malachar's curse cannot
   survive genuine cooperation."
  option "That's why you told me to trust my friends." -> dumbledore_progress_farewell
}

talk dumbledore_progress_farewell {
  "Precisely. Now go. The castle is counting on you — and so am I."
}

talk dumbledore_strange {
  "Strange how? The trials are ancient magic, Harry. They will contain
   things that do not conform to what you learned in class."
  option "It felt like the castle was helping me." -> dumbledore_castle_alive
  option "Never mind. Tell me about Malachar." -> dumbledore_malachar_deep
}

talk dumbledore_castle_alive {
  "Because it is. Hogwarts is not merely a building. It is a living
   expression of the Founders' will. And right now, it is fighting for
   its life — through you."
  option "That's a lot of pressure." -> dumbledore_progress_farewell
  option "I won't let it down." -> dumbledore_progress_farewell
}
```

---

## 3. Ron Weasley — Great Hall

```zorkscript
// ============================================================
// RON — great_hall
// Banter, loyalty, prefect_badge handoff, trial warnings.
// Voice: informal, self-deprecating humor, fierce loyalty under it.
// ============================================================

talk ron_greeting {
  "Mate! There you are. I've been sitting here for ages. The pudding's
   gone cold and the ceiling's doing this weird flickering thing — I keep
   thinking it's going to rain inside. Again."
  option "Something's wrong with the castle, Ron." -> ron_castle
  option "Have you seen Dumbledore?" -> ron_dumbledore_question
  option "Any chance you saved me some pudding?" -> ron_pudding
}

talk ron_pudding {
  "See, this is why we're friends. Priorities. Yeah, I saved you a bit.
   Well — I saved you what's left after I saved me a bit. Which is... a
   bit less than a bit."
  option "Classic Ron." -> ron_castle
  option "I need to talk to you about something serious." -> ron_castle
}

talk ron_castle {
  "Yeah, I noticed. Peeves has been dead quiet, which is properly
   terrifying when you think about it. And the suits of armor on the third
   floor are facing the wrong direction. All of them. Like they're watching
   something we can't see."
  option "Dumbledore told me what's going on." -> ron_briefing
  option "I need your help." -> ron_help_request
  excluded_flags [has_main_quest]
}

talk ron_dumbledore_question {
  "He's in his office, I think. Hasn't been at meals in days. McGonagall's
   been covering for him, but she's rubbish at hiding that she's worried."
  option "I need to get up there." -> ron_farewell_early
  option "Something's wrong with the castle." -> ron_castle
}

talk ron_farewell_early {
  "Go, go. I'll be here. Not like I've got anywhere else to be — they've
   cancelled Quidditch practice on account of the pitch trying to eat
   the goalposts."
}

// --- Post-quest dialogue ---

talk ron_briefing {
  required_flags [has_main_quest]
  "He told you WHAT? Convergence Stone? Four trials? Ancient curse?
   Blimey, Harry, we can't just have one normal year, can we? Just one.
   Exams and Quidditch and maybe a nice holiday."
  option "Will you help me?" -> ron_help_request
  option "You don't have to be involved." -> ron_opt_out
}

talk ron_opt_out {
  "Oh, shut up. 'You don't have to be involved.' When have I ever not
   been involved? When has that ever been a thing that happened? I'm in,
   you prat. Obviously I'm in."
  option "Thanks, Ron." -> ron_help_request
}

talk ron_help_request {
  "Right, well, I'm not much use at ancient curses, but I know the castle
   better than most. Six older brothers, remember? Fred and George alone
   showed me about forty secret passages. What do you need?"
  option "Have you got your prefect badge?" -> ron_badge
  option "What do you know about the trials?" -> ron_trials_warning
  option "Just watch my back." -> ron_watch_back
}

talk ron_badge {
  "My — yeah, actually. Been carrying it around. Bit embarrassing, really.
   Mum was so proud she had it polished and everything. Why?"
  option "I might need it. Can I borrow it?" -> ron_badge_give
  option "Never mind. What about the trials?" -> ron_trials_warning
}

talk ron_badge_give {
  "Take it. Honestly, you'd be doing me a favor. Percy keeps sending owls
   asking if I'm 'upholding the dignity of the position.' The dignity,
   Harry. Of a badge. That I got because everyone else said no."
  // Item given: prefect_badge
  option "You were the right choice, Ron." -> ron_badge_touched
  option "Thanks. Now, about the trials—" -> ron_trials_warning
}

talk ron_badge_touched {
  "... Yeah, well. Don't get soppy about it. Just bring it back in one
   piece. Unlike everything else I lend you."
  option "What do you know about the trials?" -> ron_trials_warning
  option "I should get going." -> ron_farewell
}

talk ron_trials_warning {
  "I don't know much, but I know this — Charlie told me once that the
   castle has rooms that don't exist until they need to. Not like the Room
   of Requirement. Older. Meaner. Rooms that test you. He said the
   portraits warned him off one on the seventh floor and he's not a bloke
   who scares easy."
  sets [ron_warned]
  option "That's not exactly reassuring." -> ron_reassure
  option "Good to know. Thanks, Ron." -> ron_farewell
}

talk ron_reassure {
  "No, it's not. But here's the thing — Charlie came back fine. Because he
   was smart enough to not go alone. So don't you go alone either. Promise
   me that."
  option "I promise." -> ron_farewell
  option "I'll try." -> ron_farewell_try
}

talk ron_farewell {
  "Right. Off you go, then. I'll be here. Or — around. If you need me,
   Harry. I mean it. Just yell."
}

talk ron_farewell_try {
  "That's not a promise, that's a hedge. Typical. Fine. Just... be careful,
   yeah?"
}

talk ron_watch_back {
  "Always have, always will. Even when your back is doing something
   monumentally stupid, like walking toward danger instead of away from it.
   Which is always."
  option "What do you know about the trials?" -> ron_trials_warning
  option "I should get going." -> ron_farewell
}
```

---

## 4. Hermione Granger — Library

```zorkscript
// ============================================================
// HERMIONE — library
// Lore, Restricted Section access, Founder research.
// Voice: precise, passionate about knowledge, impatient with laziness.
// ============================================================

talk hermione_greeting {
  "Harry! Good, you're here. I've been going through every text I can find
   on Hogwarts' founding, and there are gaps. Deliberate gaps. Entire
   chapters that reference events and then refuse to explain them. It's
   infuriating."
  option "What kind of gaps?" -> hermione_gaps
  option "I need to get into the Restricted Section." -> hermione_restricted
  option "Dumbledore told me about the Convergence Stone." -> hermione_stone
  excluded_flags [has_main_quest]
}

talk hermione_greeting_quest {
  required_flags [has_main_quest]
  "Harry! I've been researching everything I can about the Founders. There
   are references to a 'great working' — a collaborative spell unlike
   anything in recorded history. But the details are all in the Restricted
   Section, and Madam Pince won't let me within ten feet of it without
   written permission."
  option "Dumbledore gave me a permission slip." -> hermione_permission
  option "What have you found so far?" -> hermione_research
  option "Tell me about the Founders." -> hermione_founders
}

talk hermione_gaps {
  "References to a fifth collaborator. Someone who worked alongside the
   Founders and then was erased from the record. Whoever they were, the
   school went to extraordinary lengths to pretend they never existed."
  option "That might be Malachar." -> hermione_malachar_name
  option "Can you find out more?" -> hermione_restricted
}

talk hermione_malachar_name {
  "Malachar? That name appears exactly once in 'Hogwarts: A History' — in
   a footnote that says 'see Chapter 47.' There is no Chapter 47. The book
   goes from 46 to 48. Someone removed it."
  option "I need to get into the Restricted Section." -> hermione_restricted
}

talk hermione_restricted {
  "So do I. Madam Pince is immovable on the subject. We need a signed
   permission slip from a professor — and not just any professor. It has
   to be a Head of House or higher."
  option "I'll see what I can do." -> hermione_restricted_wait
  required_items [permission_slip]
  excluded_flags [restricted_unlocked]
}

talk hermione_restricted {
  required_items [permission_slip]
  "So do I. Madam Pince is immovable on the subject. We need a signed
   permission slip from a professor."
  option "Would this work?" -> hermione_permission
}

talk hermione_restricted_wait {
  "Please hurry. I can feel the answer is close — it's right there behind
   a locked gate and a very territorial librarian."
}

talk hermione_permission {
  required_items [permission_slip]
  "Is that — Harry, that's Dumbledore's signature! And it's countersigned
   by McGonagall! This isn't just permission, this is a mandate. Give me
   twenty minutes."
  option "Take your time." -> hermione_permission_later
  option "I'll come with you." -> hermione_restricted_entry
}

talk hermione_permission_later {
  "Twenty minutes, Harry. Not a second more. Meet me at the east alcove."
  sets [restricted_unlocked]
}

talk hermione_restricted_entry {
  "The Restricted Section is through the back corridor — past the Magical
   Theory shelves, left at the chained bookcase. Madam Pince keeps the
   entrance behind a curtain. Most students don't even know it's there."
  sets [restricted_unlocked]
  option "Let's go." -> hermione_restricted_farewell
}

talk hermione_restricted_farewell {
  "And Harry — don't touch anything that whispers. I mean it. Some of
   those books bite."
}

talk hermione_research {
  "Bits and pieces. The Founders didn't just build a school — they built
   a magical engine. Each of them contributed something essential. Gryffindor
   gave it courage — the willingness to act. Ravenclaw gave it wisdom — the
   capacity to learn. Hufflepuff gave it loyalty — the binding that holds.
   And Slytherin gave it ambition — the drive to grow."
  option "That's the Convergence Stone." -> hermione_stone
  option "Tell me about the Founders." -> hermione_founders
}

talk hermione_stone {
  "The Convergence Stone. Yes. I've found oblique references. It's
   described as 'the Founders' greatest and most terrible achievement.'
   One text calls it 'the weight that holds the world.' Another calls it
   'the mistake they could not unmake.' Encouraging, isn't it?"
  option "Tell me about the Founders." -> hermione_founders
  option "I need to get to the Restricted Section." -> hermione_restricted
  option "Thanks, Hermione. I should go." -> hermione_farewell
}

talk hermione_founders {
  "What most people don't understand is that the Founders weren't friends.
   Not really. They were colleagues bound by a shared vision that they
   fundamentally disagreed about. Gryffindor and Slytherin nearly killed
   each other twice. Ravenclaw thought Hufflepuff was too soft. Hufflepuff
   thought Ravenclaw was too cold. They fought constantly."
  option "Then how did they build Hogwarts?" -> hermione_founders_how
  option "Thanks. I should go." -> hermione_farewell
}

talk hermione_founders_how {
  "Because they needed each other. And they knew it. That's the remarkable
   thing. They chose to build together despite disagreeing about almost
   everything. The school exists because four people who didn't like each
   other very much decided that the work mattered more than the argument."
  option "That's actually beautiful." -> hermione_founders_beautiful
  option "Thanks, Hermione." -> hermione_farewell
}

talk hermione_founders_beautiful {
  "It is. And it's exactly what Malachar couldn't tolerate. He wanted
   harmony without conflict. Unity without difference. That's not
   cooperation — it's control."
  option "You sound like Dumbledore." -> hermione_farewell_dumbledore
  option "Thanks. I need to get moving." -> hermione_farewell
}

talk hermione_farewell {
  "Be careful, Harry. And come back if you find anything. I want to see
   it. For academic purposes. And because I'm worried about you."
}

talk hermione_farewell_dumbledore {
  "I'll take that as a compliment. Now go — and for Merlin's sake, take
   notes. If you find primary sources about the Founders in those trials
   and don't document them, I will never forgive you."
}

// --- Hermione in celestial_room (Ravenclaw trial support) ---

talk hermione_celestial {
  "Harry, look at this. The star charts on the ceiling — they're not
   decorative. They're a map. But it's incomplete. Half the constellations
   are missing."
  option "I found charts in the meditation alcove." -> hermione_charts_combine
  option "What do you think it means?" -> hermione_charts_analyze
}

talk hermione_charts_analyze {
  "The visible stars trace a path, but it dead-ends. We need the missing
   constellations to complete the route. There must be another set of
   charts somewhere — a complement to these."
  option "I'll look for them." -> hermione_charts_wait
}

talk hermione_charts_wait {
  "Try the meditation alcove, if there is one. Ravenclaw valued
   contemplation — she would have hidden knowledge in a place of stillness."
}

talk hermione_charts_combine {
  "Let me see — yes! These are the southern constellations. The ceiling
   shows the northern sky. If we overlay them... hold on..."
  option "Take your time." -> hermione_charts_result
}

talk hermione_charts_result {
  "There. The complete sky. The path traces through Orion, past Cassiopeia,
   and terminates at — it's pointing to the far wall. There must be a
   hidden passage exactly where the last star falls."
  sets [charts_combined]
  option "Brilliant, Hermione." -> hermione_charts_farewell
  option "Of course it's a hidden passage." -> hermione_charts_farewell
}

talk hermione_charts_farewell {
  "I do enjoy a good puzzle. Even one that's trying to kill us. Especially
   one that's trying to kill us, honestly."
}
```

---

## 5. Severus Snape — Potions Classroom

```zorkscript
// ============================================================
// SNAPE — potions_classroom
// Suspicious, curt, grudgingly helpful if pressed correctly.
// Voice: clipped sentences, controlled contempt, economy of words.
// ============================================================

talk snape_greeting {
  "Potter. I was not aware this classroom was on the tourist route. State
   your business or leave."
  option "I need your help with a potion." -> snape_potion_ask
  option "Dumbledore sent me." -> snape_dumbledore
  option "What do you know about the Convergence Stone?" -> snape_stone_direct
}

talk snape_dumbledore {
  "The Headmaster sends you to do many things. I am rarely impressed by
   any of them."
  option "He told me about the curse. About Malachar." -> snape_malachar
  option "I need help with a potion, Professor." -> snape_potion_ask
}

talk snape_stone_direct {
  "I know that students who ask questions above their competence tend to
   find answers above their survival. What specifically do you imagine I
   can help you with?"
  option "A Revealer Potion." -> snape_potion_ask
  option "Anything you know about the trials." -> snape_trials
}

talk snape_malachar {
  "So the Headmaster is finally telling people. How uncharacteristically
   forthcoming of him."
  option "You already knew?" -> snape_knew
  option "I need a Revealer Potion." -> snape_potion_ask
}

talk snape_knew {
  "I am Head of Slytherin House. The Slytherin trial is in my domain.
   Yes, Potter, I knew. I have known for some time. The question is
   whether you are capable of doing anything useful with the information."
  option "Help me, then." -> snape_potion_ask
  option "What can you tell me about the Slytherin trial?" -> snape_trials
}

talk snape_trials {
  "The trial of cunning is not what you think it is. It does not reward
   cleverness. It rewards judgment. Knowing when to fight, when to hide,
   and when to sacrifice something valuable for something necessary. You
   will find that difficult."
  option "Why?" -> snape_why_difficult
  option "I need a Revealer Potion." -> snape_potion_ask
}

talk snape_why_difficult {
  "Because you are your father's son. You charge. You react. You trust
   your instincts when your instincts are wrong. The Slytherin trial will
   punish that."
  option "..." -> snape_pause
  option "I'm also my mother's son." -> snape_lily
}

talk snape_pause {
  "Nothing to say? Perhaps there is hope for you yet."
  option "About that potion—" -> snape_potion_ask
}

talk snape_lily {
  "..."
  option "The Revealer Potion. Can you help me or not?" -> snape_potion_ask
}

talk snape_potion_ask {
  "A Revealer Potion. To expose hidden enchantments. At least that
   demonstrates a rudimentary understanding of what you're dealing with."
  option "Can you brew it?" -> snape_brew_refuse
  option "What ingredients do I need?" -> snape_ingredients
}

talk snape_brew_refuse {
  "I could brew it in my sleep. But I will not. If you cannot produce the
   potion yourself, you have no business using it. The trials demand
   competence, not dependence."
  option "Then tell me the ingredients." -> snape_ingredients
}

talk snape_ingredients {
  "Moonpetal — harvested under moonlight, obviously, or it's worthless.
   Powdered graphorn horn. And basilisk venom, diluted to one part in
   forty. The proportions are critical. One misstep and the result is
   toxic rather than revelatory."
  sets [snape_potion_help]
  option "Where do I find moonpetal?" -> snape_moonpetal
  option "Basilisk venom? Where am I supposed to—" -> snape_basilisk
  option "Thank you, Professor." -> snape_farewell
}

talk snape_moonpetal {
  "The greenhouse. Longbottom may be of use to you there. He is
   incompetent at most things, but he has an inexplicable talent with
   plants."
  option "And the basilisk venom?" -> snape_basilisk
  option "Thank you." -> snape_farewell
}

talk snape_basilisk {
  "You killed a basilisk in your second year, Potter. Surely you kept a
   souvenir. If not, the Chamber of Secrets is still exactly where you
   left it."
  option "And the moonpetal?" -> snape_moonpetal
  option "Right. Thanks." -> snape_farewell
}

talk snape_farewell {
  "Do not thank me. Succeed or fail on your own merit. And Potter — close
   the door on your way out. I have actual work to do."
}
```

---

## 6. Rubeus Hagrid — Hagrid's Hut / Forest Edge

```zorkscript
// ============================================================
// HAGRID — hagrid_hut, forest_edge
// Warm, worried, protective. Lore from a creature-keeper's lens.
// Voice: dropped g's, run-on warmth, fierce protectiveness.
// ============================================================

// --- Hagrid's Hut ---

talk hagrid_greeting {
  "Harry! Come in, come in. Mind Fang, he's been nervous all day — won't
   stop whinin'. Somethin's got the creatures all riled up. The thestrals
   won't come out o' the trees and I haven't seen a unicorn in weeks.
   That ain't right."
  option "What do you think is happening?" -> hagrid_worry
  option "I need your help, Hagrid." -> hagrid_help
  option "Dumbledore told me about the Convergence Stone." -> hagrid_stone
}

talk hagrid_worry {
  "The forest knows, Harry. It always knows before we do. When the
   centaurs go quiet and the acromantulas start buildin' deeper — that's
   the forest bracin' itself. Last time it was like this was... well.
   Before you were born."
  option "Before Voldemort?" -> hagrid_voldemort
  option "I need to get into the forest." -> hagrid_forest_ask
}

talk hagrid_voldemort {
  "Before him, even. The old magic's stirrin'. The kind that was here
   before the school, before the Founders. They built Hogwarts on top of
   somethin', Harry. The creatures know it. They've always known it."
  option "The Convergence Stone." -> hagrid_stone
  option "I need to get into the forest." -> hagrid_forest_ask
}

talk hagrid_stone {
  "So he told yeh. Good. I've been wantin' to talk to someone about it.
   The creatures — they feel the Stone, Harry. The unicorns are drawn to
   it. The centaurs read it in the stars. Even Fang, thick as he is,
   knows somethin's wrong down there."
  option "What do the centaurs say?" -> hagrid_centaurs
  option "I need to get into the forest." -> hagrid_forest_ask
  option "Do you have anything that might help me?" -> hagrid_wrench
}

talk hagrid_centaurs {
  "Mars is bright, they keep sayin'. Which is centaur for 'bad things are
   comin' and we're not gonna tell yeh what.' Helpful lot, centaurs. But
   Firenze — before he left — he told me the Stone was 'the anchor that
   holds the sky to the ground.' Make o' that what yeh will."
  option "I need to get into the forest." -> hagrid_forest_ask
  option "Do you have anything useful I could borrow?" -> hagrid_wrench
}

talk hagrid_help {
  "Anything, Harry. Yeh know that. What d'yeh need?"
  option "I need to get into the Forbidden Forest." -> hagrid_forest_ask
  option "Do you have any tools I could borrow?" -> hagrid_wrench
  option "What do you know about the Founders?" -> hagrid_founders
}

talk hagrid_wrench {
  "Tools? Well, I've got this wrench — enchanted, it is. Won it off a
   goblin in a card game. Opens any mundane lock, adjusts any bolt.
   Not magic locks, mind, but regular ones. Yeh'd be surprised how much
   o' this castle still runs on plain old metalwork."
  // Item given: wrench
  option "Thanks, Hagrid. I need to get into the forest." -> hagrid_forest_ask
  option "Thanks. I should go." -> hagrid_farewell_hut
}

talk hagrid_founders {
  "The Founders? I'll tell yeh what most people don't know. They didn't
   just build a school — they made a pact with the creatures of this land.
   Gryffindor treated with the centaurs. Hufflepuff befriended the
   bowtruckles and nifflers. Ravenclaw earned the respect of the
   phoenixes. And Slytherin — well, Slytherin spoke to things that
   didn't want to be spoken to."
  option "What kind of things?" -> hagrid_slytherin_creatures
  option "I need to get into the forest." -> hagrid_forest_ask
}

talk hagrid_slytherin_creatures {
  "Serpents. Basilisks. Things that live in the dark and don't take kindly
   to company. Slytherin understood 'em, though. Respected 'em. There's a
   difference between controllin' a creature and understandin' it, and
   Slytherin — for all his faults — understood."
  option "I need to get into the forest." -> hagrid_forest_ask
  option "Thanks, Hagrid." -> hagrid_farewell_hut
}

talk hagrid_farewell_hut {
  "Be careful, Harry. And come back for tea. I mean it. Yeh look like
   yeh haven't eaten."
}

// --- Forest Edge ---

talk hagrid_forest_ask {
  "The forest? Harry, I can't just let yeh in there. Not tonight. The
   creatures are spooked and the paths are shiftin'. Yeh need protection
   — real protection. Not just a wand and good intentions."
  option "I have to, Hagrid. The trials—" -> hagrid_forest_insist
  option "What kind of protection?" -> hagrid_forest_protection
}

talk hagrid_forest_insist {
  "I know, I know. But I promised Dumbledore I'd keep students out unless
   they could defend themselves. Yeh need a Shield Charm scroll — proper
   one, not the classroom version. Show me that, and I'll let yeh
   through."
  option "Where do I find one?" -> hagrid_shield_hint
  option "I have one." -> hagrid_forest_allow
    required_items [shield_charm_scroll]
}

talk hagrid_forest_protection {
  "A Shield Charm scroll. The real kind — the kind that holds against
   dark creatures, not just practice hexes. Yeh bring me one o' those,
   and I'll open the path for yeh."
  option "Where would I find one?" -> hagrid_shield_hint
  option "I already have it." -> hagrid_forest_allow
    required_items [shield_charm_scroll]
}

talk hagrid_shield_hint {
  "Try the Defence classroom, or maybe the Restricted Section. Hermione
   might know. Clever girl, that one."
  option "I'll find one." -> hagrid_forest_wait
}

talk hagrid_forest_wait {
  "I'll be right here, Harry. The forest isn't goin' anywhere.
   Unfortunately."
}

talk hagrid_forest_allow {
  required_items [shield_charm_scroll]
  "That's the one. Right — listen to me carefully. Stay on the path. Do
   NOT follow any lights that aren't yer lantern. And if yeh hear singing
   — run. That's not a person, that's a lure."
  sets [hagrid_allows_forest]
  option "I'll be careful." -> hagrid_forest_farewell
  option "What's in there?" -> hagrid_forest_warning
}

talk hagrid_forest_warning {
  "Things that are normally peaceful but aren't right now. The curse is
   agitatin' 'em. Even the bowtruckles are bitin'. Just keep yer head
   down and don't provoke nothin'."
  option "Thanks, Hagrid." -> hagrid_forest_farewell
}

talk hagrid_forest_farewell {
  "And Harry — come back. I'm serious. Yeh come back."
}
```

---

## 7. The Grey Lady (Helena Ravenclaw) — Library (CRITICAL)

```zorkscript
// ============================================================
// THE GREY LADY — library
// Reluctant, bitter, guarded. Must be persuaded gradually.
// Voice: archaic cadence, clipped anger, old grief.
// ============================================================

talk greylady_greeting {
  "Another student. Come to gawk at the ghost of Helena Ravenclaw. Or
   perhaps you want something. They always want something."
  option "I need your help." -> greylady_refuse
  option "I'm sorry to bother you." -> greylady_polite
  option "You're Helena Ravenclaw? Rowena's daughter?" -> greylady_identity
}

talk greylady_refuse {
  "Then you will be disappointed. I do not help. I haunt. There is a
   significant difference."
  option "People are in danger." -> greylady_danger
  option "This is about your mother's trial." -> greylady_mother_mention
  option "I understand. I'll go." -> greylady_leave_early
}

talk greylady_polite {
  "... Polite. That is unusual. Most of you simply demand answers as if
   I were a reference text. What do you want?"
  option "I'm looking for the Ravenclaw trial." -> greylady_trial_ask
  option "I want to understand what's happening to the castle." -> greylady_castle
}

talk greylady_identity {
  "I was. I am. I will always be, apparently. Eternity is less glamorous
   than the poets suggest."
  option "I need to find the Ravenclaw trial." -> greylady_trial_ask
  option "What was she like? Your mother?" -> greylady_mother_ask
}

talk greylady_leave_early {
  "How refreshing. A student who accepts 'no.' Come back if you develop a
   more compelling argument."
}

talk greylady_danger {
  "People are always in danger. This castle has been in danger since the
   day it was built. The Founders poured their ambitions into stone and
   called it safety. It was never safe."
  option "This is different. Malachar's curse is breaking free." -> greylady_malachar_react
  option "Your mother built the Ravenclaw trial to prevent this." -> greylady_mother_mention
}

talk greylady_castle {
  "The castle is remembering. Old magic does that — it wakes when
   threatened. The question is whether it wakes to defend itself or to
   tear itself apart."
  option "The Convergence Stone—" -> greylady_trial_ask
  option "You know about Malachar, don't you?" -> greylady_malachar_react
}

talk greylady_trial_ask {
  "The trial. Of course. Everyone wants the trial. No one wants the truth
   that comes with it."
  option "I want the truth." -> greylady_truth
  option "Just tell me where it is." -> greylady_demand
}

talk greylady_demand {
  "No. You do not command me, child. I am not a portrait to be
   interrogated. I am the daughter of Rowena Ravenclaw, and I will decide
   what I share and with whom."
  option "You're right. I'm sorry." -> greylady_apology
  option "People will die if you don't help me." -> greylady_pressure
}

talk greylady_apology {
  "... Apologies cost nothing. But yours sounded almost genuine. Ask me
   properly."
  option "Please. Help me understand." -> greylady_truth
}

talk greylady_pressure {
  "Do you think I don't know that? Do you think I haven't watched this
   castle suffer for a thousand years, knowing what lies beneath it,
   knowing what my mother built and why?"
  option "Then help me stop it." -> greylady_persuade
}

talk greylady_truth {
  "The truth is that my mother was afraid. People remember Rowena Ravenclaw
   as brilliant and composed. She was brilliant. She was never composed.
   She was terrified — of Malachar, of what the Stone could become, of
   what would happen if the binding failed."
  option "Tell me about Malachar and your mother." -> greylady_malachar_lore
  option "Where is the trial?" -> greylady_persuade
}

talk greylady_mother_mention {
  "Do not speak of my mother's trial as if you understand it. You know
   nothing of what she sacrificed to create it."
  option "Then teach me." -> greylady_persuade
  option "I know she was trying to protect the school." -> greylady_protect
}

talk greylady_mother_ask {
  "She was... complicated. Brilliant beyond measure. Cold when she needed
   to be warm. Warm when she needed to be cold. She loved this school more
   than she loved anything. Including me."
  option "I'm sorry." -> greylady_sorry_mother
  option "The trial she built—" -> greylady_persuade
}

talk greylady_sorry_mother {
  "Don't be. She made her choices. I made mine. We are both haunted by
   them — she metaphorically, I rather more literally."
  option "Will you help me find her trial?" -> greylady_persuade
}

talk greylady_protect {
  "She was trying to protect the Stone. The school was secondary. The
   Stone was everything to her — the proof that the Founders could create
   something greater than any of them alone. She would have burned the
   school to save it."
  option "Help me protect both." -> greylady_persuade
}

talk greylady_malachar_react {
  "Malachar. You dare speak that name here. In her library."
  option "I have to. He's the threat." -> greylady_malachar_lore
  option "I'm sorry. But I need to know." -> greylady_malachar_lore
}

talk greylady_persuade {
  "Why should I help you? I have watched students come and go for a
   millennium. Brave ones. Clever ones. They all believe they are special.
   Most are not."
  option "I don't think I'm special. I think I'm the one who's here." -> greylady_here
  option "Because your mother built the trial for someone like me." -> greylady_built_for
  option "Because you're tired of watching and doing nothing." -> greylady_tired
}

talk greylady_here {
  "... That may be the most honest thing a student has said to me in
   centuries. 'I'm the one who's here.' Not chosen. Not destined. Simply
   present, and willing."
  option "Will you help me?" -> greylady_reveal
}

talk greylady_built_for {
  "She built it for someone who would listen. Not to me — to the riddles,
   to the silence between the answers. Ravenclaw's trial tests whether
   you can hear what is not being said."
  option "I'm listening now." -> greylady_reveal
}

talk greylady_tired {
  "... Yes. I am tired. A thousand years of watching is long enough."
  option "Then let it end. Help me." -> greylady_reveal
}

talk greylady_reveal {
  "Very well. The Ravenclaw trial is hidden in the east tower — behind a
   wall that appears solid but responds to the question that has no answer.
   My mother called it 'the door that thinks.' You will know it when you
   see it. It will know you when you ask."
  sets [ravenclaw_entrance_known]
  option "The question with no answer?" -> greylady_riddle_hint
  option "Thank you, Helena." -> greylady_lore_offer
}

talk greylady_riddle_hint {
  "Every riddle my mother designed had a purpose beyond the answer. The
   question itself was the test — not whether you solve it, but how you
   approach it. Do not rush. Do not guess. Think."
  sets [grey_lady_clue]
  option "Tell me about Malachar and your mother." -> greylady_malachar_lore
  option "Thank you." -> greylady_farewell
}

talk greylady_lore_offer {
  "If you would hear it — there is more I can tell you. About Malachar.
   About my mother. About what really happened."
  option "Tell me everything." -> greylady_malachar_lore
  option "I have to go. But thank you." -> greylady_farewell
}

talk greylady_malachar_lore {
  "Malachar was my mother's student. Her best student. She recognized his
   brilliance before anyone else — and she recognized his pain. He was
   rejected by the other students for his blood status. She took him in.
   Mentored him. And he repaid her by trying to steal the Stone."
  sets [grey_lady_clue]
  option "She must have felt betrayed." -> greylady_betrayal
  option "Did she still care about him? After?" -> greylady_care
}

talk greylady_betrayal {
  "Betrayed. Yes. But also guilty. She believed she could have saved him
   — that if she had been kinder, more attentive, he would not have become
   what he became. She carried that guilt until the day she died. And I
   suspect, wherever she is now, she carries it still."
  option "That's why the trial tests wisdom, not knowledge." -> greylady_wisdom
  option "Thank you for telling me this." -> greylady_farewell
}

talk greylady_care {
  "She never stopped. That was her tragedy. She bound him, sealed him
   away, and then spent the rest of her life designing a trial to undo
   what she had done — because she could not accept that her student was
   beyond saving. The trial is not just a test, Potter. It is a question
   she never answered: can wisdom redeem what wisdom created?"
  option "That's... heavy." -> greylady_farewell
  option "I'll try to answer it for her." -> greylady_farewell_promise
}

talk greylady_wisdom {
  "Precisely. Knowledge is knowing the answer. Wisdom is knowing what the
   answer costs. My mother wanted someone who would count that cost before
   acting."
  option "I will." -> greylady_farewell_promise
}

talk greylady_farewell {
  "Go. And Potter — do not fail her. She has been failed enough."
}

talk greylady_farewell_promise {
  "I almost believe you. That is more than most achieve. Go."
}
```

---

## 8. Draco Malfoy — Two Encounters

```zorkscript
// ============================================================
// DRACO — serpent_hall (first encounter)
// Confrontation. Player tone determines relationship trajectory.
// Voice: sharp, defensive, aristocratic disdain masking insecurity.
// ============================================================

talk draco_serpent_greeting {
  "Well, well. Potter, skulking around the dungeons. I'd say I'm
   surprised, but I learned to stop being surprised by your complete
   disregard for rules somewhere around second year."
  option "Get out of my way, Malfoy." -> draco_hostile_path
  option "I'm not here to fight, Draco." -> draco_neutral_path
  option "What are you doing down here?" -> draco_curious_path
}

talk draco_hostile_path {
  "Make me. Go on. We both know you're dying to. The noble Harry Potter,
   always spoiling for a fight as long as he can pretend the other person
   started it."
  option "I don't have time for this." -> draco_hostile_escalate
  option "You're right. I don't want to fight." -> draco_neutral_redirect
}

talk draco_hostile_escalate {
  "Then you shouldn't have come to my part of the castle. Stupefy!"
  sets [draco_hostile]
  // Combat or block event triggers
}

talk draco_neutral_redirect {
  "... No? Losing your edge, Potter?"
  option "I'm not here for you, Malfoy." -> draco_neutral_path
}

talk draco_neutral_path {
  "Not here to fight. How disappointing. What are you here for, then?
   Because this corridor leads nowhere pleasant, and you don't strike me
   as the type who enjoys Slytherin architecture."
  option "The trials. I'm looking for the Slytherin trial." -> draco_neutral_trial
  option "None of your business." -> draco_neutral_dismiss
}

talk draco_neutral_trial {
  "The Slytherin trial. So the rumors are true — something's happening
   to the castle and Dumbledore's sent his golden boy to fix it. Typical."
  option "Something like that. Are you going to stop me?" -> draco_neutral_decision
  option "Do you know where it is?" -> draco_neutral_info
}

talk draco_neutral_dismiss {
  "Fine. Keep your secrets. I have my own."
  sets [draco_neutral]
}

talk draco_neutral_decision {
  "Stop you? No. I have better things to do than play hall monitor. But
   don't expect help, either."
  sets [draco_neutral]
  option "Fair enough." -> draco_neutral_farewell
}

talk draco_neutral_info {
  "I might. But why would I share it with you?"
  sets [draco_neutral]
  option "Forget it." -> draco_neutral_farewell
}

talk draco_neutral_farewell {
  "Good luck, Potter. You'll need it."
}

talk draco_curious_path {
  "What am I — that's none of your — ... Why do you care?"
  option "Because something's wrong and you look worried too." -> draco_curious_worry
  option "Honestly? You look like you haven't slept." -> draco_curious_concern
}

talk draco_curious_worry {
  "I'm not worried. Malfoys don't worry. We... assess situations
   strategically."
  option "And what's your strategic assessment?" -> draco_curious_assess
}

talk draco_curious_concern {
  "I... what? Don't — don't do that. Don't pretend you care about how I
   look. We're not friends, Potter."
  option "No. But that doesn't mean I want to see you hurt." -> draco_curious_vulnerability
  option "Fine. But something's wrong with the castle, and you know it." -> draco_curious_assess
}

talk draco_curious_assess {
  "The wards around the Slytherin common room failed last night. Just for
   a moment, but — I felt it. Cold like I've never felt. Not temperature.
   Something else. Something old."
  option "That's Malachar's curse." -> draco_curious_explain
}

talk draco_curious_vulnerability {
  "... You're infuriating, do you know that? You can't just — say things
   like that. To me."
  option "I just did. Now tell me what you felt in the dungeons." -> draco_curious_assess
}

talk draco_curious_explain {
  "Malachar. I've read that name in the family library. My father has a
   journal — very old, very forbidden. It mentions a wizard who nearly
   consumed Hogwarts from the inside. He was obsessed with the Stone."
  option "Your family knew about this?" -> draco_curious_family
}

talk draco_curious_family {
  "The Malfoy family has known about a great many things and done nothing
   about most of them. It's something of a tradition."
  option "Would you do something about this one?" -> draco_curious_offer
  option "I'll find you again if I need your help." -> draco_curious_farewell_open
}

talk draco_curious_offer {
  "Are you... asking me for help? Harry Potter, asking Draco Malfoy for
   help. The Prophet would have a field day."
  option "This is bigger than us, Draco." -> draco_curious_bridge
  option "Only if you can keep up." -> draco_curious_challenge
}

talk draco_curious_bridge {
  "... I'll think about it. Don't take that as a yes. Take it as a
   not-no. There's a difference."
  option "I'll find you in the Bargain Chamber." -> draco_curious_farewell_open
}

talk draco_curious_challenge {
  "Keep up? With you? Potter, I've been running circles around you since
   first year. You just never noticed because you were too busy being
   the Chosen One."
  option "Then prove it. Help me." -> draco_curious_farewell_open
}

talk draco_curious_farewell_open {
  "We'll see. Don't die before I make up my mind. That would be
   inconvenient."
}

// ============================================================
// DRACO — bargain_chamber (second encounter)
// Only accessible if NOT draco_hostile.
// Deeper character reveal, alliance possibility.
// ============================================================

talk draco_bargain_greeting {
  excluded_flags [draco_hostile]
  "You came. I was half hoping you wouldn't. It would have been easier to
   pretend this conversation never needed to happen."
  option "What do you want, Draco?" -> draco_bargain_motivation
  option "I'm glad you're here." -> draco_bargain_surprised
}

talk draco_bargain_surprised {
  "Don't. I didn't come for you. I came because — there are things at
   stake that you don't understand."
  option "Then explain them to me." -> draco_bargain_motivation
}

talk draco_bargain_motivation {
  "My father's reputation is in ruins. Our family name is worth less than
   the parchment it's printed on. And now there's a curse threatening to
   destroy the one institution that still acknowledges we exist. If
   Hogwarts falls, the Malfoy family has nothing."
  option "This is about your family?" -> draco_bargain_family
  option "There's more to it than that." -> draco_bargain_deeper
}

talk draco_bargain_family {
  "Everything is about my family, Potter. That's something you wouldn't
   understand, seeing as yours is — ... I'm sorry. That was beneath me."
  option "Go on." -> draco_bargain_deeper
  option "Yeah. It was." -> draco_bargain_tension
}

talk draco_bargain_tension {
  "I know. I said I'm sorry. I don't say that often, so you might want
   to appreciate the rarity."
  option "Noted. Keep talking." -> draco_bargain_deeper
}

talk draco_bargain_deeper {
  "My father is a broken man, Potter. He sits in that manor and stares at
   portraits of ancestors who did great things, and he knows he'll never
   be one of them. He had one chance to prove our family's worth and he
   chose the wrong side. I won't make the same mistake."
  option "This isn't about sides, Draco." -> draco_bargain_sides
  option "So help me. Prove the Malfoy name means something." -> draco_bargain_offer_alliance
}

talk draco_bargain_sides {
  "Everything is about sides. The difference is whether you're choosing
   a side or letting one choose you. I'm tired of being chosen."
  option "Then choose this. Help me stop Malachar." -> draco_bargain_offer_alliance
  option "I can't make that choice for you." -> draco_bargain_refuse_path
}

talk draco_bargain_offer_alliance {
  "An alliance. Between a Potter and a Malfoy. If our grandfathers could
   see this, they'd collectively have an aneurysm."
  option "Is that a yes?" -> draco_bargain_accept
  option "I need to know I can trust you." -> draco_bargain_trust
}

talk draco_bargain_trust {
  "Trust. There's a word I don't use much. I can't give you a guarantee,
   Potter. What I can give you is this: Malachar's curse threatens my
   home. I will fight anything that threatens my home. Right now, that
   puts us on the same side. Is that enough?"
  option "It's enough." -> draco_bargain_accept
  option "No. I need more than convenience." -> draco_bargain_refuse_path
}

talk draco_bargain_accept {
  "Then it's done. I know the Slytherin dungeons better than anyone alive.
   I know where the trial entrance is — I've seen it, behind the false
   wall in the lower corridor. I'll show you when you're ready."
  sets [draco_allied]
  option "Thank you, Draco." -> draco_bargain_farewell_allied
}

talk draco_bargain_farewell_allied {
  "Don't thank me. And don't tell anyone about this conversation. I have
   a reputation to maintain. What's left of it."
}

talk draco_bargain_refuse_path {
  "Fine. I tried. Don't say I didn't try."
  sets [draco_neutral]
  option "Draco—" -> draco_bargain_farewell_neutral
  option "Good luck on your own." -> draco_bargain_farewell_neutral
}

talk draco_bargain_farewell_neutral {
  "Save it. You know where to find me if you change your mind. I'll be
   in the dungeons, pretending none of this happened."
}
```

---

## 9. Ron — Guardian Hall (Gryffindor Trial)

```zorkscript
// ============================================================
// RON — guardian_hall (Gryffindor trial)
// Trapped, injured, frightened. Emotional core of the trial.
// Voice: fear under bravado, humor as defense mechanism, raw honesty.
// ============================================================

talk ron_guardian_greeting {
  "H-Harry? Is that you? Please tell me that's you and not another one
   of those — those things. I can't — my leg, mate. I think it's broken.
   Maybe worse."
  option "It's me. I'm here." -> ron_guardian_relief
  option "What happened?" -> ron_guardian_explain
  option "Can you walk?" -> ron_guardian_walk
}

talk ron_guardian_relief {
  "Oh, thank Merlin. Thank Merlin. I followed you in — I know you said
   to wait, but I couldn't just sit there while you — and then the floor
   gave out and I fell and something grabbed my leg and—"
  option "Breathe, Ron. You're safe now." -> ron_guardian_calm
  option "Let me see your leg." -> ron_guardian_injury
}

talk ron_guardian_explain {
  "I came after you. Stupid, I know. You don't have to say it. The
   corridor behind you — it collapsed. I tried to climb through and
   something pulled me down. Like hands, but cold. Made of stone. They
   let go when I screamed, but my leg..."
  option "Let me look at it." -> ron_guardian_injury
}

talk ron_guardian_walk {
  "Walk? Harry, I can barely sit. Every time I move, it feels like
   someone's driving a spike through my knee. I've tried. I can't."
  option "I have a healing potion." -> ron_guardian_potion
    required_items [healing_potion]
  option "There has to be something I can do." -> ron_guardian_no_potion
    excluded_flags [has_healing_potion]
}

talk ron_guardian_calm {
  "Right. Breathing. I'm breathing. That's a start. Better than the
   alternative."
  option "Let me see your leg." -> ron_guardian_injury
}

talk ron_guardian_injury {
  "It's bad. I can tell because I don't want to look at it, and in my
   experience that's a reliable indicator. If Mum could see me now she'd
   kill me, and then she'd kill you for letting me come."
  option "I have a healing potion." -> ron_guardian_potion
    required_items [healing_potion]
  option "I don't have anything to help you right now." -> ron_guardian_no_potion
}

talk ron_guardian_potion {
  required_items [healing_potion]
  "You — really? You're giving me your healing potion? Harry, you might
   need that. The trial isn't over."
  option "You need it more." -> ron_guardian_potion_give
  option "Take it, Ron. That's not a request." -> ron_guardian_potion_insist
}

talk ron_guardian_potion_give {
  "... You're an idiot. The best kind of idiot, but still an idiot."
  // healing_potion consumed
  option "Drink it." -> ron_guardian_healed
}

talk ron_guardian_potion_insist {
  "Fine. Fine. Don't have to tell me twice. Well, you did tell me twice,
   but—"
  // healing_potion consumed
  option "Just drink it." -> ron_guardian_healed
}

talk ron_guardian_healed {
  "... Oh. Oh, that's — yeah. That's much better. Still sore, but I can
   move. I can actually move."
  sets [ron_rescued]
  option "Can you walk out of here?" -> ron_guardian_walk_out
  option "Stay here until I finish the trial." -> ron_guardian_stay
}

talk ron_guardian_walk_out {
  "I think so. Slowly. Very slowly. And possibly with a lot of
   complaining."
  option "Wouldn't have it any other way." -> ron_guardian_emotional
}

talk ron_guardian_stay {
  "I'll wait. But Harry — come back, yeah? I mean it. Don't you dare
   die in some ancient magic trial and leave me to explain it to
   Hermione."
  option "I'll come back." -> ron_guardian_emotional
}

talk ron_guardian_emotional {
  "Harry. I know I make jokes about everything. It's what I do. But I
   need you to know — if I'd lost you today — if I was sitting here and
   you didn't come — I don't know what I'd..."
  option "You didn't lose me." -> ron_guardian_farewell
  option "I know, Ron." -> ron_guardian_farewell
}

talk ron_guardian_farewell {
  "Yeah. Right. Enough of that. Go be a hero. I'll be here, nursing my
   dignity back to health. It's in worse shape than my leg was."
}

// --- If player has no potion and chooses to leave ---

talk ron_guardian_no_potion {
  "Nothing? That's — okay. That's okay. I'll manage. I've had worse.
   Actually, no, I haven't. This is definitely the worst."
  option "I'll come back with help. I promise." -> ron_guardian_leave
  option "I have to keep going, Ron. I'm sorry." -> ron_guardian_abandon
}

talk ron_guardian_leave {
  "Go. Find something. I'll be here. Not like I have a choice."
  option "I'll be back as fast as I can." -> ron_guardian_leave_farewell
}

talk ron_guardian_leave_farewell {
  "I know you will. Just — hurry, yeah? It's dark in here and the
   walls are making noises I don't like."
}

talk ron_guardian_abandon {
  "You're — you're leaving me here? Harry, I — ... Right. The mission.
   The trial. I get it. I do. Just — go. Before I say something I'll
   regret."
  sets [ron_abandoned]
  option "Ron—" -> ron_guardian_abandon_farewell
  option "..." -> ron_guardian_abandon_farewell
}

talk ron_guardian_abandon_farewell {
  "Just go."
}
```

---

## 10. Neville Longbottom — Greenhouse

```zorkscript
// ============================================================
// NEVILLE — greenhouse
// Nervous, knowledgeable, underestimated. Comes alive with plants.
// Voice: hesitant starts, gains confidence when talking botany.
// ============================================================

talk neville_greeting {
  "Oh! Harry! Sorry, you — you startled me. I was repotting the
   Venomous Tentacula and it does not like surprises. Neither do I,
   actually."
  option "Sorry, Neville. I need your help." -> neville_help
  option "What do you know about moonpetal?" -> neville_moonpetal_direct
  option "Have you noticed anything strange with the plants?" -> neville_strange
}

talk neville_strange {
  "Strange? Harry, the Whomping Willow tried to uproot itself this
   morning. Professor Sprout found it twenty feet from its original
   position. The mandrakes won't stop screaming — even with earmuffs, I
   can feel it in my teeth. Something underground is agitating them."
  option "It's the Convergence Stone." -> neville_stone
  option "I need moonpetal for a potion." -> neville_moonpetal_direct
}

talk neville_stone {
  "The — really? I thought that was just a legend. Gran used to mention
   it, but she mentions a lot of things, most of them complaints about
   the Ministry."
  option "It's real. And I need moonpetal to help stop what's happening." -> neville_moonpetal_direct
}

talk neville_help {
  "Me? I mean — sure. I'll try. I'm not very good at the whole
   adventuring thing, but if it's about plants, I might actually know
   something useful for once."
  option "It's about plants. Moonpetal, specifically." -> neville_moonpetal_direct
}

talk neville_moonpetal_direct {
  "Moonpetal! Oh, I know moonpetal. It's — sorry, this is going to sound
   like a lecture. Moonpetal only blooms under direct moonlight, and it
   has to be harvested within the first three minutes of bloom or the
   petals lose their magical properties. You need fresh air and an
   unobstructed sky — the greenhouse roof blocks it."
  option "Where can I find some?" -> neville_moonpetal_location
  option "How do I harvest it?" -> neville_moonpetal_harvest
}

talk neville_moonpetal_location {
  "There's a patch growing wild near the edge of the forest — Hagrid
   showed me once. And there might be some in the courtyard garden, if
   Luna hasn't picked it all for her Nargle repellent. She uses a lot
   of moonpetal for that."
  option "How do I harvest it properly?" -> neville_moonpetal_harvest
  option "Thanks, Neville." -> neville_farewell
}

talk neville_moonpetal_harvest {
  "Cut the stem at a diagonal, below the second leaf node. Use a silver
   blade if you have one — steel bruises the petals and they lose potency.
   And talk to it while you cut. I know that sounds mad, but moonpetal
   responds to intent. If you're harvesting with purpose, it... cooperates."
  option "Talk to the plant." -> neville_talk_plant
  option "Where do I find it?" -> neville_moonpetal_location
  option "Thanks, Neville. Really." -> neville_farewell
}

talk neville_talk_plant {
  "I know how it sounds. But plants aren't stupid, Harry. They're just
   quiet. Moonpetal especially — it was bred by Helga Hufflepuff herself.
   She believed every living thing deserved to be asked, not just taken
   from."
  option "Hufflepuff grew moonpetal?" -> neville_hufflepuff
  option "I'll keep that in mind." -> neville_farewell
}

talk neville_hufflepuff {
  "She was brilliant with plants. Most people remember her for loyalty
   and kindness, but she was the finest herbologist of her age. Half the
   magical species in this greenhouse descend from her original cultivars.
   I think about that a lot, actually."
  option "You'd have been her favorite student." -> neville_compliment
  option "Thanks, Neville." -> neville_farewell
}

talk neville_compliment {
  "I — you think? I mean, that's — nobody's ever said — ... thanks,
   Harry. That actually means a lot."
  option "I should get going." -> neville_farewell
}

talk neville_farewell {
  "Good luck. And Harry — if you need anything else plant-related, come
   find me. It's the one thing I'm actually good at. Might as well use it."
}
```

---

## 11. Luna Lovegood — Courtyard

```zorkscript
// ============================================================
// LUNA — courtyard
// Dreamy, perceptive, oddly profound. Sees things others dismiss.
// Voice: wandering cadence, non-sequiturs that circle back to insight.
// ============================================================

talk luna_greeting {
  "Hello, Harry. You have an unusual number of Wrackspurts around your
   head today. That usually means you're thinking too hard about the wrong
   thing."
  option "Luna, have you noticed anything strange?" -> luna_strange
  option "I need help with the Ravenclaw trial." -> luna_ravenclaw
  option "What's a Wrackspurt again?" -> luna_wrackspurt
}

talk luna_wrackspurt {
  "They're invisible creatures that float into your ears and make your
   brain go fuzzy. Most people have a few. You have about seventeen,
   which is a personal record. Something must be very confusing for you
   right now."
  option "You could say that." -> luna_strange
  option "The Ravenclaw trial — do you know anything?" -> luna_ravenclaw
}

talk luna_strange {
  "Oh, yes. The Nargles are absolutely frantic. They've been trying to
   warn people for days, but nobody listens to Nargles. They're quite
   offended, actually. I left them some pudding to apologize on behalf
   of the school."
  option "What are they warning about?" -> luna_nargles_warning
  option "Luna, I need to ask you about the Ravenclaw trial." -> luna_ravenclaw
}

talk luna_nargles_warning {
  "The ground is humming. Can you feel it? Put your hand on the stones.
   Right here. The castle is talking, Harry. Most people can't hear it
   because they're too busy making noise themselves. It's saying 'help.'"
  option "I'm trying to help. That's why I need the Ravenclaw trial." -> luna_ravenclaw
  option "You can hear the castle?" -> luna_castle_hear
}

talk luna_castle_hear {
  "Not hear, exactly. Feel. It's like the difference between listening to
   someone speak and standing next to them while they cry. You don't need
   words for the second one."
  option "The Ravenclaw trial, Luna. Please." -> luna_ravenclaw
}

talk luna_ravenclaw {
  "The trial of wisdom. I've thought about it, you know. Not because
   anyone asked me to, but because it seemed like the sort of thing worth
   thinking about. My mother would have loved it."
  option "Do you know anything that could help?" -> luna_riddle
  option "Your mother studied Ravenclaw's work?" -> luna_mother
}

talk luna_mother {
  "She studied everything. She was a researcher. She died trying to
   understand something that wasn't ready to be understood. I think
   Rowena Ravenclaw would have liked her. They had the same flaw —
   curiosity without caution."
  option "I'm sorry, Luna." -> luna_sorry
  option "The trial — can you help me?" -> luna_riddle
}

talk luna_sorry {
  "Don't be. She died doing what she loved. There are worse ways to go
   than being consumed by wonder."
  option "The riddle — do you know anything?" -> luna_riddle
}

talk luna_riddle {
  "I know that Ravenclaw's riddles aren't meant to be solved the way you
   solve an equation. They're meant to be sat with. Like a cat. You don't
   solve a cat. You just... let it happen."
  option "That's surprisingly helpful." -> luna_riddle_detail
  option "Can you be more specific?" -> luna_riddle_detail
}

talk luna_riddle_detail {
  "The entrance asks a question with no answer. Most people try to answer
   it anyway, because they're afraid of silence. But silence is an answer,
   isn't it? The absence of a thing is still a thing. Like how a hole is
   defined by what isn't there."
  sets [luna_riddle_hint]
  option "So the answer is... not answering?" -> luna_riddle_confirm
  option "Thank you, Luna." -> luna_nargle_quest
}

talk luna_riddle_confirm {
  "The answer is accepting that not everything needs an answer. That's
   different from not answering. One is giving up. The other is wisdom."
  option "Got it. Thanks, Luna." -> luna_nargle_quest
}

talk luna_nargle_quest {
  "Harry — while you're exploring the castle, if you happen to find any
   Nargle nests, could you leave them alone? They're just frightened.
   Everything is frightened right now. Even the things pretending not
   to be."
  option "I'll be gentle with the Nargles." -> luna_farewell
  option "I'll try." -> luna_farewell
}

talk luna_farewell {
  "Good luck, Harry. I think the castle is rooting for you. In its own
   very old, very confused way."
}
```

---

## 12. Dobby — Kitchens

```zorkscript
// ============================================================
// DOBBY — kitchens
// Ecstatic, loyal, self-sacrificing. Emotional intensity at 11.
// Voice: third person, breathless excitement, fierce devotion.
// ============================================================

talk dobby_greeting {
  "HARRY POTTER! Harry Potter has come to the kitchens! Dobby is so
   happy! Dobby was hoping Harry Potter would come! Dobby has been
   waiting and waiting and the other elves told Dobby to stop bouncing
   but Dobby cannot help it!"
  option "It's good to see you too, Dobby." -> dobby_calm
  option "Dobby, I need your help." -> dobby_help
  option "Is everything okay down here?" -> dobby_problem
}

talk dobby_calm {
  "Dobby is — Dobby will try to be calm. Dobby is calm. Dobby is very
   calm. (Dobby is not calm at all, sir.)"
  option "What's going on in the kitchens?" -> dobby_problem
  option "I need to ask you something." -> dobby_help
}

talk dobby_problem {
  "The cold stores, sir! They is locked! Frozen shut — and not the good
   kind of frozen that keeps the butter fresh, the bad kind that makes
   the doors scream when you touch them! Dobby has tried everything but
   Dobby's magic is not strong enough. The food is going bad and the
   elves cannot cook without ingredients and if the students cannot eat
   then Dobby has FAILED, sir!"
  option "Slow down. What kind of magic locked them?" -> dobby_cold_stores
  option "I might be able to help with that." -> dobby_quest
}

talk dobby_cold_stores {
  "Old magic, sir. The kind that was here before the elves. Before the
   kitchens. Dobby can feel it in the walls — cold and angry and very,
   very old. It is like the castle's bones have turned to ice."
  option "It's Malachar's curse. It's affecting the whole school." -> dobby_malachar
  option "A warming charm might break through." -> dobby_quest
}

talk dobby_malachar {
  "Dobby does not know this Malachar, sir. But Dobby knows bad magic
   when Dobby feels it. Dobby lived with bad magic for many years, sir.
   With the Malfoys. Dobby knows the taste of it."
  option "Can I help with the cold stores?" -> dobby_quest
}

talk dobby_help {
  "Harry Potter wants to help Dobby? DOBBY should be helping HARRY
   POTTER! What does Harry Potter need? Dobby will do anything! Dobby
   will fight! Dobby will cook! Dobby will iron his own ears if it
   helps!"
  option "Please don't iron your ears. I need information." -> dobby_info
  option "The cold stores — I can help with that, and then I need your help." -> dobby_quest
}

talk dobby_info {
  "Information! Dobby has information! Dobby knows every corner of this
   castle, sir! The elves go everywhere — through the walls, through the
   floors. We sees things that wizards do not see!"
  option "Do you know anything about a hidden trial? Under the castle?" -> dobby_trial_ask
  option "Let me help you with the cold stores first." -> dobby_quest
}

talk dobby_trial_ask {
  "Dobby knows there is something beneath the basement kitchens. The
   oldest elves — the ones who have been here for centuries — they
   whisper about a yellow door. A door that smells like fresh bread and
   warm earth. But Dobby cannot tell Harry Potter where it is until the
   cold stores is fixed, sir. Dobby cannot think properly when the
   butter is spoiling!"
  option "Fair enough. Tell me about the cold stores." -> dobby_quest
}

talk dobby_quest {
  "The cold stores is behind the big iron door at the back of the
   kitchens. The ice magic has sealed them shut. A proper warming charm —
   not the little ones, the real kind — might break the seal. But Dobby
   cannot cast wizard-level warming charms, sir. Dobby's magic is
   different."
  option "I'll handle it. Show me the door." -> dobby_quest_accept
  option "I'll come back when I have a warming charm ready." -> dobby_quest_later
}

talk dobby_quest_accept {
  "Harry Potter is the greatest wizard Dobby has ever met! Dobby always
   says so! The other elves think Dobby is biased but Dobby does not
   care!"
  option "Lead the way, Dobby." -> dobby_quest_go
}

talk dobby_quest_later {
  "Dobby will wait, sir! Dobby is very good at waiting! Dobby waited
   twelve years for freedom, sir. Dobby can wait for a warming charm."
}

talk dobby_quest_go {
  "This way, sir! Mind the soup vat, sir! And the ceiling, sir! It is
   lower than wizards expect!"
}

// --- After quest completion ---

talk dobby_quest_complete {
  "Harry Potter did it! The stores is open! The butter is SAVED! Dobby
   is so grateful, sir, Dobby will never forget this! Never ever!"
  option "Now — about that hidden trial." -> dobby_trial_reveal
  option "It was nothing, Dobby." -> dobby_nothing
}

talk dobby_nothing {
  "It was NOT nothing, sir! It was EVERYTHING! But — yes. Dobby promised
   information. Dobby keeps promises."
  option "The Hufflepuff trial?" -> dobby_trial_reveal
}

talk dobby_trial_reveal {
  "The yellow door, sir. It is below the wine cellar, behind the oldest
   barrel — the one that has never been opened because it hums when you
   touch it. That is not wine in that barrel, sir. That is an entrance.
   Dobby has felt it. It smells like loyalty, sir. Like belonging."
  sets [dobby_helped]
  option "Thank you, Dobby. This means a lot." -> dobby_farewell
}

talk dobby_farewell {
  "Dobby is happy to help Harry Potter. Always. Harry Potter freed Dobby.
   Dobby will never stop repaying that, sir. Not ever."
}
```

---

## 13. The Ghosts — Nick, Fat Friar, Bloody Baron

```zorkscript
// ============================================================
// NEARLY HEADLESS NICK — great_hall / corridors
// Pompous, helpful, slightly tragic. Castle historian.
// ============================================================

talk nick_greeting {
  "Ah, Harry! A pleasure, as always. I must say, the castle is in quite
   a state. I haven't seen this level of magical disturbance since the
   Great Plumbing Incident of 1742 — though that was less 'existential
   threat' and more 'unfortunate miscalculation with an Aguamenti charm.'"
  option "Nick, what do you know about the Gryffindor trial?" -> nick_trial
  option "Have you noticed anything unusual?" -> nick_unusual
  option "What was Godric Gryffindor like?" -> nick_gryffindor
}

talk nick_unusual {
  "Unusual? My dear boy, I am a ghost. My entire existence is unusual.
   But yes — the Bloody Baron has been even more uncommunicative than
   normal, which I did not think was possible. And the staircases are
   moving with purpose. As if they're guiding people. Or herding them."
  option "The Gryffindor trial — do you know where it is?" -> nick_trial
}

talk nick_gryffindor {
  "A man of extraordinary bravery and equally extraordinary temper. He
   once challenged a dragon to a duel over a matter of honor. The dragon
   declined, which Godric took as a personal insult. He was... not a
   subtle man. But his heart was true."
  option "And his trial?" -> nick_trial
}

talk nick_trial {
  "The trial of courage. I know a few things about it — perks of being
   dead for five hundred years and having nothing to do but eavesdrop on
   paintings. The trial is in the upper floors — I've felt it pulsing
   behind the walls near the seventh-floor corridor. It tests not just
   whether you are brave, but whether your bravery serves others."
  option "What does that mean?" -> nick_courage_meaning
  option "How do I find the entrance?" -> nick_entrance
}

talk nick_courage_meaning {
  "Charging into danger is easy. Any fool can do that — and many have,
   to their detriment. Gryffindor's trial asks: are you brave for yourself,
   or are you brave because someone needs you to be? The difference is
   everything."
  option "How do I find the entrance?" -> nick_entrance
  option "Thanks, Nick." -> nick_farewell
}

talk nick_entrance {
  "Look for a tapestry depicting the Battle of Wyvern Hill. Gryffindor
   is the knight with the broken visor — he never could keep his armor
   in one piece. Speak his name to the tapestry. If you are worthy, it
   will respond."
  option "Thank you, Nick." -> nick_farewell
}

talk nick_farewell {
  "Good luck, Harry. And if you happen to see the Headless Hunt on your
   travels, do tell them I said hello. From a considerable distance.
   With a wall between us, preferably."
}

// ============================================================
// THE FAT FRIAR — near kitchens / Hufflepuff areas
// Gentle, warm, encouraging. Radiates kindness.
// ============================================================

talk friar_greeting {
  "Hello there, dear boy! Don't be alarmed by the state of things —
   the castle has weathered worse than this. Well, perhaps not worse,
   exactly. But certainly things of a comparable... no, this might
   actually be the worst. But we mustn't dwell on that!"
  option "Do you know about the Hufflepuff trial?" -> friar_trial
  option "Were you alive when the trials were created?" -> friar_history
  option "How do I prepare for what's coming?" -> friar_guidance
}

talk friar_history {
  "Goodness, no! The trials predate me by several centuries. But I have
   spoken with older ghosts who spoke with older ghosts who spoke with
   people who were actually there. The chain of gossip is quite reliable,
   I assure you."
  option "What did they say about the Hufflepuff trial?" -> friar_trial
}

talk friar_guidance {
  "Prepare your heart more than your wand. The trials are not combat
   examinations. They test character. The greatest preparation you can
   make is to know, truly know, what you value and what you would
   sacrifice to protect it."
  option "And the Hufflepuff trial specifically?" -> friar_trial
}

talk friar_trial {
  "Helga's trial tests loyalty. Not the easy kind — not 'stand with your
   friends when it's convenient.' The hard kind. The kind where loyalty
   costs you something. Where being faithful means giving up something
   you want."
  option "What should I expect?" -> friar_expect
  option "Where is it?" -> friar_location
}

talk friar_expect {
  "You will be asked to choose between something valuable and someone
   who needs your help. That is all I can say. Helga designed her trial
   to be experienced, not explained. Explaining it would defeat the
   purpose entirely."
  option "Where do I find it?" -> friar_location
  option "Thank you, Friar." -> friar_farewell
}

talk friar_location {
  "Below the kitchens. There is a place where the castle goes deeper
   than it should — deeper than any blueprint accounts for. Helga built
   there because she believed the most important things are always
   foundations. Unseen. Unappreciated. But holding everything else up."
  option "Thank you." -> friar_farewell
}

talk friar_farewell {
  "Go with kindness, dear boy. It is the most powerful magic there is,
   and the only one that never runs out."
}

// ============================================================
// THE BLOODY BARON — dungeons
// Intimidating, terse, haunted by guilt. Information through menace.
// ============================================================

talk baron_greeting {
  "... You are brave to approach me, Potter. Or foolish. The distinction
   matters less than people think."
  option "I need to know about the Slytherin trial." -> baron_trial
  option "The castle is in danger." -> baron_danger
  option "Can you control Peeves?" -> baron_peeves
}

talk baron_danger {
  "I know. I have known for longer than you have been alive. The curse
   sings in the stones. I hear it constantly. It sounds like regret."
  option "The Slytherin trial — where is it?" -> baron_trial
  option "Can you help?" -> baron_help_refuse
}

talk baron_help_refuse {
  "I am dead, boy. My helping days are behind me. What I can do is tell
   you what I know, and what I know is this: do not enter the Slytherin
   trial expecting a fight. Salazar's test is not about strength."
  option "Then what is it about?" -> baron_trial
}

talk baron_trial {
  "Cunning. But not the petty kind. Not tricks and schemes. Salazar
   valued the cunning of survival — knowing when to advance, when to
   retreat, and when to let your enemy believe they have won. The trial
   will present you with impossible choices. The correct answer is
   usually the one that feels like losing."
  option "That's unsettling." -> baron_unsettling
  option "Where is the entrance?" -> baron_entrance
}

talk baron_unsettling {
  "Good. If you are unsettled, you are paying attention. Comfort is the
   enemy of cunning."
  option "Where's the entrance?" -> baron_entrance
}

talk baron_entrance {
  "Deep in the dungeons. Beyond the Slytherin common room, there is a
   corridor that most students believe is a dead end. It is not. The wall
   responds to Parseltongue — or, failing that, to a demonstration of
   Slytherin values that the wall finds... convincing."
  option "Thank you." -> baron_farewell
  option "About Peeves—" -> baron_peeves
}

talk baron_peeves {
  "Peeves fears me. Use my name if he blocks your path. Say 'The Bloody
   Baron sends his regards.' He will move. If he does not, tell me, and
   I will deal with him personally."
  sets [baron_name_known]
  option "Thank you, Baron." -> baron_farewell
  option "What about the Slytherin trial?" -> baron_trial
}

talk baron_farewell {
  "Do not thank me. Survive. That is thanks enough."
}
```

---

## 14. Fred & George Weasley — Entrance Hall

```zorkscript
// ============================================================
// FRED & GEORGE — entrance_hall
// Mischievous, finish each other's sentences, chaos merchants.
// Voice: rapid-fire ping-pong dialogue, irrepressible humor.
// ============================================================

talk twins_greeting {
  "FRED: Harry! Just the man we wanted to see.
   GEORGE: Or avoid, depending on your perspective.
   FRED: We've been doing a bit of entrepreneurial work—
   GEORGE: —during an existential crisis—
   FRED: —because capitalism never sleeps, Harry."
  option "What are you selling?" -> twins_shop
  option "Do you know anything about secret passages?" -> twins_passages
  option "This really isn't the time." -> twins_serious
}

talk twins_serious {
  "GEORGE: He's right, Fred. Very serious situation.
   FRED: Absolutely. Doom and gloom.
   GEORGE: ...
   FRED: ...
   GEORGE: We're still selling things, though."
  option "Fine. What have you got?" -> twins_shop
  option "The passages. Talk." -> twins_passages
}

talk twins_shop {
  "FRED: First up — Magical Candy! Our own special blend. Eat one and
   you'll feel invincible for about thirty seconds.
   GEORGE: You won't actually be invincible.
   FRED: Important legal distinction, that.
   GEORGE: Second — Peruvian Darkness Powder! Throw it, and everything
   within ten feet goes pitch black. Very useful for dramatic exits.
   FRED: Five Galleons for both. Mates' rates."
  option "Deal. Here's five Galleons." -> twins_buy
    required_items [galleons_5]
  option "I don't have the gold right now." -> twins_no_gold
  option "What about those secret passages?" -> twins_passages
}

talk twins_buy {
  required_items [galleons_5]
  "FRED: Pleasure doing business!
   GEORGE: The candy is the round one. The powder is the bag.
   FRED: Do NOT mix them up.
   GEORGE: Fred mixed them up once.
   FRED: We don't talk about that."
  // Items given: magical_candy, peruvian_darkness_powder
  option "Thanks. Secret passages?" -> twins_passages
  option "Cheers." -> twins_farewell
}

talk twins_no_gold {
  "GEORGE: No gold, no goods. We're philanthropists, Harry—
   FRED: —but not that kind of philanthropists.
   GEORGE: Come back when you're flush. We'll be here.
   FRED: Not going anywhere. Literally. The doors are stuck."
  option "What about secret passages?" -> twins_passages
  option "I'll be back." -> twins_farewell
}

talk twins_passages {
  "FRED: Now you're speaking our language.
   GEORGE: The Marauder's Map is with you, obviously—
   FRED: —but the map doesn't show everything. There are passages even
   Dad's old map missed. Older ones.
   GEORGE: There's one behind the mirror on the fourth floor. Leads
   down to a junction we've never explored because—
   FRED: —it smelled like old magic and bad decisions.
   GEORGE: Which is usually a sign to either run away—
   FRED: —or charge in headfirst. We recommend the latter."
  sets [twins_hint]
  option "Thanks, you two." -> twins_farewell
  option "About those items you're selling—" -> twins_shop
}

talk twins_farewell {
  "FRED: Good luck, Harry!
   GEORGE: Don't die!
   FRED: If you do die, can we have your broom?
   GEORGE: FRED.
   FRED: What? It's a Firebolt!"
}
```

---

## 15. Ghostly Student — Crossroads of Need (Hufflepuff Trial)

```zorkscript
// ============================================================
// GHOSTLY STUDENT — crossroads_of_need (Hufflepuff trial)
// Young, lost, desperate. A loyalty test in human form.
// Voice: fragile, earnest, the kind of sadness that hurts to hear.
// ============================================================

talk ghostly_student_greeting {
  "Please — wait. Don't go. Everyone goes. Everyone walks past. I've
   been here so long, and nobody stops."
  option "I'm not going anywhere. Who are you?" -> ghostly_identity
  option "What happened to you?" -> ghostly_story
  option "I'm in a hurry—" -> ghostly_dismiss
}

talk ghostly_identity {
  "My name is... I was... I was a student. A Hufflepuff. I came down here
   looking for something, years ago. Decades? I don't know anymore. Time
   doesn't work properly in the trials."
  option "What were you looking for?" -> ghostly_story
  option "Are you... dead?" -> ghostly_dead
}

talk ghostly_dead {
  "I don't know. I'm something. Not alive. Not properly dead. Stuck.
   Like a letter that was sent but never delivered. I've been waiting
   at this crossroads for someone to help me."
  option "How can I help?" -> ghostly_story
}

talk ghostly_story {
  "I had a locket. A golden locket. It was my mother's — the only thing
   I had left of her. I dropped it somewhere in these tunnels when I ran.
   I ran because I was scared and I shouldn't have run. If I had it back,
   I think... I think I could move on."
  option "I have a golden locket." -> ghostly_locket_offer
    required_items [golden_locket]
  option "I'll look for it." -> ghostly_wait
  option "I can't help you. I'm sorry." -> ghostly_dismiss
}

talk ghostly_locket_offer {
  required_items [golden_locket]
  "That's — that's it. That's my mother's locket. I can feel it. Where
   did you — it doesn't matter. You found it. You actually found it."
  option "Here. It's yours." -> ghostly_give_locket
  option "I might need this." -> ghostly_keep_locket
}

talk ghostly_give_locket {
  "You're giving it to me? You don't have to — I know it's valuable. I
   know you probably need it for the trial. But... it's all I have. It's
   all I ever had."
  // golden_locket consumed
  sets [loyalty_proven]
  option "It was always yours." -> ghostly_resolution
}

talk ghostly_resolution {
  "I can feel it. I can feel her. She's waiting. She's been waiting this
   whole time and I didn't know. Thank you. I don't even know your name,
   and you gave me the most important thing anyone has ever given me."
  option "It's Harry." -> ghostly_farewell
  option "Go find her." -> ghostly_farewell
}

talk ghostly_farewell {
  "Harry. I'll remember that name. Wherever I'm going — I'll remember.
   The path ahead is open for you now. You've earned it. Truly."
}

talk ghostly_keep_locket {
  "I understand. You need it. The trial needs it. I just thought — no.
   You're right. The living must come first. That's what Professor
   Hufflepuff would have said."
  option "I'm sorry." -> ghostly_keep_farewell
  option "Wait — take it." -> ghostly_give_locket
}

talk ghostly_keep_farewell {
  "Don't be sorry. You made a choice. The trial knows. It always knows.
   Go. The other path will open for you. It's harder, but it's there."
}

talk ghostly_dismiss {
  "Oh. You're like the others, then. In a hurry. Always in a hurry.
   I'll wait. I'm good at waiting. I've had a lot of practice."
  option "Wait — hold on." -> ghostly_story
}

talk ghostly_wait {
  "I'll be here. I don't go anywhere. I can't. But if you find it —
   please come back. Please."
}
```

---

## 16. Spectral Wounded Stranger — Wounded Stranger Room

```zorkscript
// ============================================================
// SPECTRAL WOUNDED STRANGER — wounded_stranger room
// Ambiguous, in pain, tests compassion without framing it as a test.
// Voice: labored breathing, broken sentences, desperate dignity.
// ============================================================

talk stranger_greeting {
  "Who's — who's there? Don't come closer. I don't know if I'm — I
   might be dangerous. I don't know what I am anymore."
  option "I'm not going to hurt you." -> stranger_reassure
  option "What happened to you?" -> stranger_story
  option "Are you part of the trial?" -> stranger_meta
}

talk stranger_reassure {
  "That's what the last one said. Before the corridor ate them. I'm not
   being dramatic — it literally ate them. The walls closed and they
   were gone."
  option "I'm still here. Let me help." -> stranger_help
  option "What happened to you?" -> stranger_story
}

talk stranger_story {
  "I came down here chasing something. A sound. Like crying, but not
   human. The castle crying. I wanted to find it and make it stop. And
   then the floor opened and I fell and something cut me — something I
   couldn't see — and now I can't move and I can't feel my..."
  option "Let me see the wound." -> stranger_help
  option "I have something that might help." -> stranger_offer
}

talk stranger_meta {
  "Part of the — I don't know what a trial is. I just know I'm hurt
   and I've been here for what feels like days and I'm cold. So cold."
  option "Let me help you." -> stranger_help
}

talk stranger_help {
  "You'd help me? You don't know me. You don't know if I'm real, or a
   trap, or — why would you help?"
  option "Because you're hurt." -> stranger_offer
  option "Because it's the right thing to do." -> stranger_offer
  option "I don't need a reason." -> stranger_offer
}

talk stranger_offer {
  "I'll take anything. Anything. The cold is getting worse and I can
   feel myself fading. Like I'm being erased."
  option "Here — a healing potion." -> stranger_heal
    required_items [healing_potion]
  option "Try this — it's magical candy. It might help." -> stranger_candy
    required_items [magical_candy]
  option "I don't have anything." -> stranger_nothing
}

talk stranger_heal {
  required_items [healing_potion]
  "A healing potion? For me? You're using a healing potion on a stranger
   in a dungeon. You're either very kind or very foolish."
  // healing_potion consumed
  option "Maybe both." -> stranger_healed
  option "Drink it." -> stranger_healed
}

talk stranger_healed {
  "Oh... oh, the warmth. I'd forgotten what warmth felt like. The wound
   is — it's closing. I can see my hands again. I can feel my hands."
  sets [stranger_healed]
  option "Good. Can you stand?" -> stranger_reward
}

talk stranger_reward {
  "I can do more than stand. I can — I remember now. I remember why I
   came down here. I was carrying this. I think it was meant for you."
  // Item given: hufflepuff_charm
  option "What is it?" -> stranger_charm_explain
  option "Thank you." -> stranger_farewell
}

talk stranger_charm_explain {
  "A Hufflepuff charm. I don't know what it does, exactly. But it's
   warm, like the potion was. Like kindness is. I think it will know
   what to do when the time comes."
  option "Will you be all right?" -> stranger_farewell
}

talk stranger_candy {
  required_items [magical_candy]
  "Candy? I — at this point, I'll try anything."
  // magical_candy consumed
  option "It's enchanted. Should take the edge off." -> stranger_candy_effect
}

talk stranger_candy_effect {
  "It's... sweet. And warm. Not as strong as a proper potion, but — I
   can move my fingers again. I can think clearly. Thank you. Thank you."
  sets [stranger_healed]
  option "Can you get out of here?" -> stranger_candy_reward
}

talk stranger_candy_reward {
  "I think so. Slowly. Here — take this. I found it on the ground before
   I was hurt. I think the castle wanted someone to have it."
  // Item given: hufflepuff_charm
  option "Thank you. Be careful getting out." -> stranger_farewell
}

talk stranger_nothing {
  "Nothing. Of course. No — I'm sorry. That wasn't fair. You came. You
   stopped. That's more than anyone else has done."
  option "I'll come back. I promise." -> stranger_nothing_farewell
}

talk stranger_nothing_farewell {
  "If you can. I'll try to hold on. The cold is patient, but so am I."
}

talk stranger_farewell {
  "Go. And remember this — not the trial, not the magic. This. The
   moment you chose to help someone who couldn't help you back. That's
   the real test. It always was."
}
```

---

## Cross-Reference: Flags Set by Dialogue

| Flag | Set By | Location |
|------|--------|----------|
| `knows_gargoyle_password` | McGonagall | great_hall |
| `has_main_quest` | Dumbledore | dumbledore_office |
| `knows_stone_lore` | Dumbledore | dumbledore_office |
| `dumbledore_malachar_info` | Dumbledore (return visit) | dumbledore_office |
| `ron_warned` | Ron | great_hall |
| `restricted_unlocked` | Hermione | library |
| `charts_combined` | Hermione | celestial_room |
| `snape_potion_help` | Snape | potions_classroom |
| `hagrid_allows_forest` | Hagrid | forest_edge |
| `ravenclaw_entrance_known` | The Grey Lady | library |
| `grey_lady_clue` | The Grey Lady | library |
| `draco_hostile` | Draco | serpent_hall |
| `draco_neutral` | Draco | serpent_hall / bargain_chamber |
| `draco_allied` | Draco | bargain_chamber |
| `ron_rescued` | Ron | guardian_hall |
| `ron_abandoned` | Ron | guardian_hall |
| `luna_riddle_hint` | Luna | courtyard |
| `dobby_helped` | Dobby | kitchens |
| `baron_name_known` | Bloody Baron | dungeons |
| `twins_hint` | Fred & George | entrance_hall |
| `loyalty_proven` | Ghostly Student | crossroads_of_need |
| `stranger_healed` | Spectral Stranger | wounded_stranger |

## Items Distributed via Dialogue

| Item | Given By | Condition |
|------|----------|-----------|
| `enchanted_lantern` | Dumbledore | Main quest briefing |
| `permission_slip` | Dumbledore | Main quest briefing |
| `invisibility_cloak` | Dumbledore | Main quest briefing |
| `prefect_badge` | Ron | Asked for it |
| `wrench` | Hagrid | Asked for tools |
| `magical_candy` | Fred & George | 5 galleons |
| `peruvian_darkness_powder` | Fred & George | 5 galleons |
| `hufflepuff_charm` | Spectral Stranger | Healed with potion or candy |
