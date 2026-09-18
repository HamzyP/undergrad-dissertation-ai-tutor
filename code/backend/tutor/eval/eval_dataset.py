"""
Full built-in evaluation dataset for the philosophy RAG tutor.
See sample_dataset.py for the minimal example showing the expected structure.

Each entry has:
  query         — a student question the RAG system should answer
  topic         — the lecture/module topic (used to set session context)
  grading_notes — bullet points the correctness metric checks for

ALL grading notes are grounded in the five SEP corpus articles:
  liberalism, mill-moral-political, mill, democracy, rousseau
and the two lecture transcripts (liberalism.vtt, rep-democracy.vtt).
Questions about thinkers or topics not covered in those sources are
marked OUT-OF-SCOPE and graded on graceful degradation only.
"""

EVAL_DATASET = [

    # ---------------------------------------------------------------
    # DEFINITIONAL
    # ---------------------------------------------------------------

    # --- Liberty concepts (liberalism article §1) ---
    {
        "query": "What is negative liberty according to Isaiah Berlin?",
        "topic": "Liberalism",
        "grading_notes": (
            "- Negative liberty is the area within which a person can act unobstructed by others.\n"
            "- A person is free to the degree that no person or body of persons interferes with their activity.\n"
            "- You lack political liberty only if prevented from attaining a goal by deliberate human interference — natural inability (blindness, lack of skill) does not count.\n"
            "- The key distinction: coercion requires deliberate interference by other humans, not mere inability or natural obstacle."
        ),
    },
    {
        "query": "What is positive liberty?",
        "topic": "Liberalism",
        "grading_notes": (
            "- Positive liberty has two main forms in the liberalism article: the autonomy conception and the effective-power conception.\n"
            "- Autonomy conception (Green, Kant, Mill): a person is free only if self-directed and autonomous — not subject to compulsions, critically reflecting on ideals, not following custom unreflectively.\n"
            "- This is an 'exercise-concept': freedom requires actually exercising one's higher capacities, not merely the absence of interference.\n"
            "- Effective-power conception (Tawney): freedom as the ability to act or the effective power to pursue one's ends — closely tied to material resources.\n"
            "- On the positive view an addict or a very poor person can be considered unfree even if no one directly stops them."
        ),
    },
    {
        "query": "What is republican liberty?",
        "topic": "Liberalism",
        "grading_notes": (
            "- Republican (neo-Roman) liberty holds that the opposite of freedom is domination, not merely actual interference.\n"
            "- To be unfree is to be subject to the potentially capricious will or idiosyncratic judgement of another — even if that power is never exercised.\n"
            "- Republican liberty focuses on 'defenseless susceptibility to interference, rather than actual interference' (Pettit).\n"
            "- The mere possibility of arbitrary interference limits liberty, even when no interference occurs.\n"
            "- It differs from both Berlin's negative liberty (which requires actual interference) and Greenian positive liberty (which requires realising rational autonomy)."
        ),
    },
    {
        "query": "How does negative liberty differ from positive liberty?",
        "topic": "Liberalism",
        "grading_notes": (
            "- Negative liberty is the absence of deliberate human interference; positive liberty is the capacity for self-direction or effective power to act.\n"
            "- Under negative liberty an addict or a poor person faces no unfreedom if no one stops them; under positive liberty they are unfree because driven by compulsion or lacking effective power.\n"
            "- Negative liberty concerns which options are foreclosed by others' actions; positive liberty concerns whether one is actually able to govern oneself.\n"
            "- The two can support different policy conclusions: positive liberty may justify state intervention to develop capacities or redistribute resources."
        ),
    },

    # --- Classical vs New liberalism (liberalism article §2) ---
    {
        "query": "What is classical liberalism?",
        "topic": "Liberalism",
        "grading_notes": (
            "- Classical liberalism holds that liberty and private property are intimately connected — a market economy based on private property is uniquely consistent with individual liberty.\n"
            "- Private property is seen either as an embodiment of freedom itself (freedom to contract, sell labour, invest) or as practically necessary to protect liberty by dispersing power.\n"
            "- Classical liberals endorse a minimal state whose chief role is protecting liberty and property rights.\n"
            "- Most 19th-century classical liberals still allowed licensing, health and safety regulations, and banking regulation; the spectrum runs from near-anarchist to allowing a modest social minimum."
        ),
    },
    {
        "query": "What is the difference between classical liberalism and new liberalism?",
        "topic": "Liberalism",
        "grading_notes": (
            "- Classical liberalism holds that liberty and private property are intimately connected and favours a minimal state.\n"
            "- New (or 'revisionist' or welfare-state) liberalism challenges that intimate connection, accepting state intervention to address poverty and inequality.\n"
            "- New liberals lost faith in the free market's ability to sustain prosperous equilibrium (drawing on Keynes) and gained faith in democratic government as a corrective.\n"
            "- The deepest new-liberal objection: property rights foster unjust inequality of power and entrench merely formal equality that fails to secure equal positive liberty for the working class.\n"
            "- Mill's On Liberty contains seeds of this view: personal and economic liberty have distinct justifications."
        ),
    },
    {
        "query": "What is Rawls's difference principle?",
        "topic": "Liberalism",
        "grading_notes": (
            "- The difference principle (from the liberalism article's social-justice section) states: a just basic structure arranges social and economic inequalities so they are to the greatest advantage of the least well-off representative group.\n"
            "- The default is equal distribution of income and wealth; only inequalities that benefit the least advantaged are just.\n"
            "- The principle constitutes a public recognition of reciprocity: no social group should advance at the cost of another.\n"
            "- Rawls later insisted welfare-state capitalism is not enough; justice requires a property-owning democracy with wide diffusion of ownership, or market socialism.\n"
            "- Note: the corpus discusses this in the liberalism article; there is no standalone Rawls SEP article in the knowledge base."
        ),
    },
    {
        "query": "What is political liberalism in Rawls?",
        "topic": "Liberalism",
        "grading_notes": (
            "- Political liberalism (Rawls's later position) holds that liberalism should not be a comprehensive moral or philosophical doctrine covering the whole of ethics, value, or metaphysics.\n"
            "- Modern societies contain 'reasonable pluralism' — many competing comprehensive doctrines that cannot all be true.\n"
            "- Political liberalism aims to be neutral between these doctrines by providing a political framework without entering sectarian debates.\n"
            "- Rawls's political conception is largely restricted to constitutional principles upholding basic civil liberties and the democratic process.\n"
            "- This contrasts with 'comprehensive liberalism', which rests on a broader theory of the good, the self, or human nature."
        ),
    },

    # --- Mill (mill-moral-political article) ---
    {
        "query": "What does Mill mean by the harm principle?",
        "topic": "Mill on Liberty",
        "grading_notes": (
            "- Mill's harm principle: the sole end for which mankind are warranted in interfering with the liberty of any person is self-protection — to prevent harm to others.\n"
            "- A person's own good (physical or moral) is not sufficient warrant for coercion.\n"
            "- Mill distinguishes paternalistic restrictions (for B's own benefit), moralistic restrictions (to ensure B acts morally), and harm-principle restrictions (to prevent harm to someone other than B).\n"
            "- 'Harm' is not the same as 'mere offence': genuine harm requires violation or risk of violation of important interests in which people have rights.\n"
            "- Harm prevention is necessary but not sufficient: a utilitarian calculation of costs and benefits must still be made."
        ),
    },
    {
        "query": "What does Mill mean by paternalism?",
        "topic": "Mill on Liberty",
        "grading_notes": (
            "- Paternalism is restricting a person's liberty for their own good rather than to prevent harm to others.\n"
            "- Mill's harm principle prohibits paternalistic coercion: a person's own good is not a sufficient warrant.\n"
            "- The prohibition does not extend to children or adults with very limited deliberative or normative competence — liberal principles apply only when sufficient rational development is in place.\n"
            "- The state may remonstrate, persuade, warn, or entreat, but not compel, a person to act for their own benefit."
        ),
    },
    {
        "query": "What is Mill's argument against censorship?",
        "topic": "Mill on Liberty",
        "grading_notes": (
            "- Mill gives two main rationales for free speech. First, a truth-tracking rationale: a censored opinion might be true; even if false it may contain part of the truth; even if wholly false, suppression prevents true beliefs from being a 'living truth' rather than 'dead dogma'.\n"
            "- Second, a deliberative rationale: freedoms of thought and discussion are necessary for fulfilling our nature as progressive beings capable of knowledge (not merely true belief).\n"
            "- In many-sided matters (politics, morality) truth is many-sided; only the reconciling and combining of opposites yields the whole truth.\n"
            "- Speech may be restricted only when the circumstances of expression constitute a direct instigation to a harmful act (a 'clear and present danger'-style threshold).\n"
            "- Mill's argument implies even competent, well-intentioned censorship is epistemically damaging."
        ),
    },
    {
        "query": "How does Mill distinguish between higher and lower pleasures?",
        "topic": "Mill on Utilitarianism",
        "grading_notes": (
            "- Mill modifies Bentham's quantitative hedonism by introducing qualitative differences between pleasures.\n"
            "- Higher pleasures are those caused by the exercise of higher faculties (intellectual, creative, moral); lower pleasures by lower capacities.\n"
            "- Competent judges — those who have experienced both types — consistently prefer higher pleasures even at the cost of greater suffering.\n"
            "- 'It is better to be Socrates dissatisfied than a fool satisfied' captures the claim that quality can outweigh quantity.\n"
            "- Debate exists whether higher pleasures are (a) subjective mental states caused by higher activities or (b) those objective activities themselves."
        ),
    },
    {
        "query": "What is sanction utilitarianism in Mill?",
        "topic": "Mill on Utilitarianism",
        "grading_notes": (
            "- Sanction utilitarianism defines wrongness indirectly: an action is wrong if and only if some kind of sanction (punishment, social censure, or the reproaches of conscience) ought to be applied to it.\n"
            "- 'We do not call anything wrong unless we mean to imply that a person ought to be punished in some way or other for doing it.'\n"
            "- Whether sanctions ought to be applied depends on a direct utilitarian calculation of the costs and benefits of sanctioning the conduct.\n"
            "- This makes sanction utilitarianism an indirect utilitarianism: rightness and wrongness are defined not in terms of the utility of the action itself but of the utility of applying sanctions.\n"
            "- Justice is a species of duty on this view; not every suboptimal act is wrong — only those it would be optimal to sanction."
        ),
    },
    {
        "query": "What is Mill's proof of the principle of utility and why is it controversial?",
        "topic": "Mill on Utilitarianism",
        "grading_notes": (
            "- Mill argues that the only proof of desirability is desire: each person desires their own happiness for its own sake, therefore happiness as such is desired for its own sake from the standpoint of humanity.\n"
            "- He addresses apparent counterexamples (e.g., virtue desired for its own sake) by arguing they are consistent: people come to desire virtue as part of happiness, not in conflict with it.\n"
            "- The main objection: Mill commits a fallacy of composition — from 'each person desires their own happiness' he concludes 'all desire general happiness', which does not follow.\n"
            "- A further objection: even if the proof works for happiness, it cannot establish that happiness alone is desirable, since people also desire things like virtue for their own sakes.\n"
            "- Mill's response appeals to human sympathy and identification with broader interests: the happiness of others becomes constitutive of one's own happiness."
        ),
    },
    {
        "query": "Why does Mill defend individuality in On Liberty?",
        "topic": "Mill on Liberty",
        "grading_notes": (
            "- Mill gives a two-pronged argument. For individuals: different individuals have different natures and must be given space to discover and develop their own personalities and ways of living.\n"
            "- 'Human nature is not a machine to be built after a model...but a tree, which requires to grow and develope itself on all sides, according to the tendency of the inward forces which make it a living thing.'\n"
            "- For society: it is good for society that individuals develop their own character — experiments in living benefit everyone.\n"
            "- It is a central feature of a good life that it be a life chosen for oneself; the manner in which people act matters as much as what they do.\n"
            "- The mass uniformity of democratic societies threatens individuality through social pressure, not only through law."
        ),
    },

    # --- Rousseau (rousseau article) ---
    {
        "query": "What is Rousseau's concept of amour de soi?",
        "topic": "Rousseau",
        "grading_notes": (
            "- Amour de soi is the instinctual drive toward self-preservation that all creatures possess.\n"
            "- It directs individuals to attend to basic biological needs: food, shelter, warmth.\n"
            "- On Rousseau's view, humans as part of a benevolent creator's design are individually well-equipped to satisfy these natural needs.\n"
            "- Amour de soi is natural and benign; it is paired with pitié (compassion), the passion directing us to relieve others' suffering without endangering self-preservation.\n"
            "- It is contrasted with amour propre, which is socially generated and potentially harmful."
        ),
    },
    {
        "query": "How does Rousseau's amour propre differ from amour de soi?",
        "topic": "Rousseau",
        "grading_notes": (
            "- Amour de soi is the natural, benign drive toward self-preservation present in all creatures.\n"
            "- Amour propre is a socially generated form of self-regard that makes the need to be recognised by others as having value and to be treated with respect central to one's felt interests.\n"
            "- Amour propre emerges with sexual competition in small settled communities when humans begin comparing themselves with rivals.\n"
            "- On the traditional reading (Discourse on Inequality), amour propre is wholly negative — people seek to be esteemed superior to others, creating conflict and corruption.\n"
            "- More recent readings (drawing on Emile) allow a balanced form: amour propre is also the source of rational capacities and can take a benign character through proper social organisation and education."
        ),
    },
    {
        "query": "What is the general will in Rousseau?",
        "topic": "Rousseau",
        "grading_notes": (
            "- The general will is the collective will of the citizen body taken as a whole, directed toward the common good.\n"
            "- A state is legitimate only if guided by the general will; in obeying laws expressing the general will each citizen is subject only to their own will and thus remains free.\n"
            "- The general will must come 'from all and apply to all': laws must be general in application, universal in scope, naming no particular individuals.\n"
            "- There is a tension between a democratic conception (what citizens decide together in sovereign assembly) and a transcendent conception (the common interest existing in abstraction from what anyone actually wants).\n"
            "- Rousseau distinguishes the general will from the will of all, which is merely the aggregate of private individual interests."
        ),
    },
    {
        "query": "Why does Rousseau argue that man is born free but is everywhere in chains?",
        "topic": "Rousseau",
        "grading_notes": (
            "- Rousseau's claim is that human beings are naturally free but actual societies impose illegitimate constraints.\n"
            "- The Discourse on Inequality traces how material interdependence (agriculture, metallurgy, private property) and amour propre combine to generate endemic conflict and political structures that entrench inequality.\n"
            "- The Social Contract aims to show how legitimate authority can reconcile freedom with the need for collective governance.\n"
            "- Rousseau identifies multiple senses of freedom (natural, civil, moral, republican) and argues that obedience to the general will — a law one prescribes to oneself — is not subjection but the fullest expression of moral freedom.\n"
            "- The passage immediately following the opening sentence raises the paradox: Rousseau claims he can show how subjection can be made legitimate."
        ),
    },
    {
        "query": "Why does Rousseau reject representative government?",
        "topic": "Rousseau",
        "grading_notes": (
            "- Rousseau rejects the Hobbesian idea that people's legislative will can be vested in a representative who acts with authority over them.\n"
            "- Handing over the general right of ruling oneself to another amounts to an abdication of moral agency — a form of slavery.\n"
            "- Representatives legislate on topics citizens have not themselves deliberated on, binding citizens in terms they never agreed to.\n"
            "- The desire to be represented is a symptom of moral decline and loss of civic virtue: citizens who want representatives prefer comfort over self-rule.\n"
            "- However, Rousseau does accept that government (administration, executive decrees) can be delegated — he rejects representation of sovereignty (law-making), not all delegation of power."
        ),
    },
    {
        "query": "What is Rousseau's argument that obedience to the general will makes one free?",
        "topic": "Rousseau",
        "grading_notes": (
            "- Rousseau holds that freedom has multiple senses; on the 'moral freedom' reading, obedience to a law one prescribes to oneself is not heteronomy but the fullest expression of autonomy.\n"
            "- In a well-ordered republic, the democratic process enables citizens to discover the content of the general will they share; in obeying the resulting law each citizen obeys only their own will.\n"
            "- Those who refuse the general will are 'forced to be free' — their private inclination is overridden in favour of the will they hold as citizens.\n"
            "- On the republican-freedom reading, being subject to the general will provides protection from the arbitrary power of any particular person — which is itself a form of freedom.\n"
            "- Many commentators find the argument that outvoted citizens are still obeying their own will unconvincing."
        ),
    },
    {
        "query": "What is Rousseau's doctrine of civil religion?",
        "topic": "Rousseau",
        "grading_notes": (
            "- In the final chapter of The Social Contract Rousseau argues a civil religion is necessary for patriotism and social solidarity.\n"
            "- Its tenets: affirmation of a supreme being and the afterlife; the principle that the just prosper and the wicked are punished; the sanctity of the social contract and its laws.\n"
            "- The toleration provision: all willing to tolerate others should themselves be tolerated; those insisting there is no salvation outside their church cannot be citizens, since they cannot tolerate others.\n"
            "- The civil religion dogmas are designed to be affirmable by adherents of different faiths — an overlapping-consensus structure.\n"
            "- Notably, Rousseau argues that early Christianity is unsuited to fostering civic virtue, and that atheists cannot be trusted to obey the law without fear of divine punishment."
        ),
    },

    # --- Democracy (democracy article) ---
    {
        "query": "Why does Mill argue that democracy is preferable to other forms of government?",
        "topic": "Representative Democracy",
        "grading_notes": (
            "- Mill's case is primarily instrumental/consequentialist: democracy produces relatively good laws and policies by being more responsive to subjects' rights and interests.\n"
            "- Democracy also improves the character of participants: in non-democratic societies citizens become passive, which breeds vulnerability to oppression; democratic participation develops deliberative, intellectual, and creative capacities.\n"
            "- Mill's criterion for good government has a perfectionist dimension: it should promote active and autonomous forms of life, not merely efficient administration.\n"
            "- Representative rather than direct democracy is preferred because complexity makes direct democracy impractical and because citizens are removed one step from policy-making, reducing the effects of inexperience.\n"
            "- Historical evidence is also invoked: free democratic states have outperformed monarchies and oligarchies."
        ),
    },
    {
        "query": "What is the problem of democratic participation and why is it vexing?",
        "topic": "Democracy",
        "grading_notes": (
            "- The democracy article identifies three distinct components. First, the expertise/virtue problem (Plato): some people are more intelligent, informed, and morally superior — why should the ignorant rule?\n"
            "- Second, the division-of-labour problem: if everyone devotes themselves to politics, there is little energy for other essential specialised tasks.\n"
            "- Third, the rational-voting problem (Downsian model): an individual's vote almost never decides outcomes; rational agents therefore have little incentive to become well-informed.\n"
            "- Together these create a self-defeating tension: equal political power implies egalitarian participation that may prevent effective governance, but a reasonable division of labour undermines political equality."
        ),
    },
    {
        "query": "What is the Condorcet jury theorem and how does it bear on democratic authority?",
        "topic": "Democracy",
        "grading_notes": (
            "- The Condorcet jury theorem (CJT) is a mathematical result showing that when three assumptions hold, the probability that a majority supports the correct decision increases toward certainty as the number of voters grows.\n"
            "- The three assumptions: (1) competence — each voter is more likely than not to identify the correct decision; (2) sincerity — voters vote for what they actually believe; (3) independence — votes are statistically independent.\n"
            "- With 10,000 voters each at 51% competence, the probability the majority selects the correct outcome is approximately 99.97%.\n"
            "- Applied to democracy, CJT provides an epistemic justification: majority rule is a reliable truth-tracker about the public interest.\n"
            "- Critics argue the assumptions are rarely satisfied in actual democracies: voters' opinions are not independent (persuasion, coalitions), and the competence assumption is questionable."
        ),
    },
    {
        "query": "What is Arrow's impossibility theorem and why does it pose a challenge for democracy?",
        "topic": "Democracy",
        "grading_notes": (
            "- Arrow's theorem shows that no social choice function can simultaneously satisfy unlimited domain, non-dictatorship, transitivity and completeness, the Pareto principle, and independence of irrelevant alternatives when there are three or more alternatives.\n"
            "- The implication is that there is no principled way to aggregate individual preferences into a coherent collective preference under these plausible conditions.\n"
            "- If voting cycles are pervasive, outcomes may be determined by agenda-setting and strategic manipulation rather than fairness.\n"
            "- The challenge is most acute for views that justify democracy by reference to preference-aggregation; instrumental views (Mill) are less threatened since democracy is defended by outcomes rather than by aggregating preferences.\n"
            "- Debate continues about how common cycles actually are and whether intensity-of-preference accounts modify the critique."
        ),
    },
    {
        "query": "What is the boundary problem in democratic theory?",
        "topic": "Democracy",
        "grading_notes": (
            "- The boundary problem asks who has the right to participate in democratic decisions — both within a jurisdiction (adults? residents? all affected?) and across jurisdictions (why are state boundaries drawn as they are?).\n"
            "- Activities in one state often affect people in another (pollution, economic spillovers), raising the question of whether those affected have a claim to participate even if not residents.\n"
            "- One answer is national self-determination: boundaries are determined by a principle allowing political communities to organise according to their own values.\n"
            "- But self-determination might enable non-democratic institutions; and there are proposed grounds for boundary revision (serious injustice within a country, existence of permanent sectionally-defined minorities)."
        ),
    },
    {
        "query": "What is the difference between trustees and delegates in the ethics of representation?",
        "topic": "Democracy",
        "grading_notes": (
            "- The distinction is Hannah Pitkin's. Trustees rely on their own independent judgment in carrying out their duties as representatives.\n"
            "- Delegates defer to the preferences and judgments of their constituents.\n"
            "- The trustee norm is supported by the recognition that officials are often in a better position than ordinary citizens to make well-reasoned, well-informed political decisions.\n"
            "- The delegate norm reflects democratic accountability: people authorise representatives, so representatives should enact the people's judgments.\n"
            "- Pitkin argues the appropriate norm varies by context: citizens should set society's aims (delegate role), while representatives should determine the means to achieve those aims (trustee role)."
        ),
    },
    {
        "query": "How does the elite theory of democracy respond to the problem of democratic participation?",
        "topic": "Democracy",
        "grading_notes": (
            "- Elite theorists (e.g., Schumpeter) argue that citizen ignorance and apathy are predictable, reasonable, and in fact desirable rather than a failure to be corrected.\n"
            "- On their view democracy is primarily a peaceful mechanism for choosing and replacing rulers, not a form of genuine self-rule.\n"
            "- Citizens participate mainly by voting out leaders who perform badly; since they know little, they are not effectively the ruling part.\n"
            "- Elite theory is compatible with instrumental defences of democracy but opposed to intrinsic justifications based on liberty, public justification, or equality.\n"
            "- An alternative 'defensible epistocracy' view holds that representative democracy already functions as an epistocracy because officials have far higher pivotality and accountability incentives than ordinary voters."
        ),
    },
    {
        "query": "How does instrumentalism differ from non-instrumentalism as justifications for democracy?",
        "topic": "Democracy",
        "grading_notes": (
            "- Instrumentalism justifies democracy by its outcomes: it produces better laws, protects rights, promotes economic growth, prevents famine, and improves the character of participants.\n"
            "- Non-instrumentalism holds that some forms of collective decision-making are morally desirable independent of their consequences — e.g., as an expression of equal political liberty, public justification, or social equality.\n"
            "- Liberty-based non-instrumentalism: each person ought to have an equal voice in collective decisions to have equal control over the environment that affects them — this is a right, not merely instrumentally valuable.\n"
            "- Mill is primarily an instrumentalist; Habermas's public-justification view and equality-based views are non-instrumentalist.\n"
            "- The distinction matters practically: Arrow's impossibility theorem and the rational-ignorance problem are more damaging for instrumentalists than for non-instrumentalists."
        ),
    },

    # ---------------------------------------------------------------
    # COMPARATIVE
    # ---------------------------------------------------------------
    {
        "query": "How does Mill's representative democracy differ from Rousseau's direct democracy?",
        "topic": "Representative Democracy",
        "grading_notes": (
            "- Rousseau rejected representation of sovereignty entirely: handing over one's legislative will to a representative is a form of slavery and moral abdication.\n"
            "- Mill accepted that the scale of modern societies makes direct democracy impractical and advocated representative democracy.\n"
            "- Both share concern about citizen competence (echoing Plato): Rousseau addresses it through civic education, constraints on factionalism, and the role of a legislator; Mill addresses it through representative filtering and proposed plural votes for the educated.\n"
            "- Rousseau's republic relies on citizens sharing a common identity and will; Mill's theory is more permissive of diversity and pluralism.\n"
            "- Rousseau favoured elective aristocracy for day-to-day administration; Mill favoured a broadly enfranchised representative system."
        ),
    },
    {
        "query": "How does Mill's utilitarianism differ from Bentham's?",
        "topic": "Mill on Utilitarianism",
        "grading_notes": (
            "- Bentham treats all pleasures as commensurable by quantity alone (intensity, duration, probability, etc.); Mill introduces qualitative differences between higher and lower pleasures.\n"
            "- Bentham endorses psychological egoism — each person aims only at their own happiness; Mill rejects this and allows disinterested concern for virtue and the happiness of others.\n"
            "- Mill's indirect sanction utilitarianism means that not every suboptimal act is wrong — only those it would be optimal to sanction.\n"
            "- Mill incorporates perfectionist elements: happiness involves exercising distinctly human capacities, connecting well-being to human excellence.\n"
            "- Mill's liberalism provides constraints on state interference that Bentham's more direct maximising framework does not."
        ),
    },
    {
        "query": "How would Mill's harm principle apply to drug criminalisation?",
        "topic": "Mill on Liberty",
        "grading_notes": (
            "- Drug use that affects only the user is a self-regarding action; under the harm principle it cannot be prohibited on the grounds that it harms the user alone.\n"
            "- Criminalisation for the user's own good is paternalism, which Mill rejects — a person's own good is not sufficient warrant for coercion.\n"
            "- The state may legitimately restrict drug supply or use if it causes harm to others (violence, harm to dependants, public costs).\n"
            "- Mill allows persuasion, education, remonstration, and warning — just not coercion — to discourage self-harmful behaviour.\n"
            "- The boundary is difficult to draw since almost any action can be argued to affect others, which is one of the main objections to the harm principle."
        ),
    },
    {
        "query": "How would Mill's concern about the tyranny of the majority apply to social media content moderation?",
        "topic": "Mill on Liberty",
        "grading_notes": (
            "- Mill warned that democratic majorities exercise tyranny not only through law but through social pressure, public opinion, and custom.\n"
            "- Content moderation that removes minority viewpoints at the behest of majority sentiment replicates this mechanism of social tyranny.\n"
            "- Mill's free-speech argument counsels against suppressing unpopular opinions: even false views force defenders of the truth to sharpen their reasons; suppression risks turning true beliefs into dead dogma.\n"
            "- The harm principle is the relevant test: only content that directly harms others — not merely offends — can be legitimately removed on Mill's view.\n"
            "- Mill's argument does not rule out all content moderation; direct incitement to harmful acts falls within the harm-principle exception."
        ),
    },
    {
        "query": "How would Rousseau's theory of the general will apply to referendum results that harm a minority?",
        "topic": "Rousseau",
        "grading_notes": (
            "- The will of all (the aggregate of private individual interests, i.e. the majority vote) need not coincide with the general will (the common good of the community as a whole).\n"
            "- A majority voting its own interests at the expense of a minority expresses the will of all, not the general will.\n"
            "- For Rousseau, a result that does not track the common good lacks the authority to bind — it is not legitimate law.\n"
            "- Rousseau's solution is structural: civic virtue, economic equality, and the avoidance of factionalism are prerequisites for the general will to emerge from voting.\n"
            "- The general will's formality requirement (laws must be general in scope and apply to all) also provides a check: laws targeting particular minorities cannot express the general will."
        ),
    },
    {
        "query": "What is the main objection to Mill's harm principle?",
        "topic": "Mill on Liberty",
        "grading_notes": (
            "- The line between self-regarding and other-regarding actions is extremely difficult to draw: almost any action can be argued to affect others.\n"
            "- Critics argue the concept of 'harm' is undefined and can be stretched — either to justify almost any restriction or to block almost any intervention depending on how harm is construed.\n"
            "- The principle may be too permissive for those who think laws against offence or immorality can be legitimate.\n"
            "- The distinction between harm and mere offence is not always clear, which makes the principle difficult to apply consistently."
        ),
    },
    {
        "query": "What objections have been raised against Rousseau's general will?",
        "topic": "Rousseau",
        "grading_notes": (
            "- The general will is ambiguous: it is unclear whether it is what citizens actually decide together or a transcendent standard independent of their actual choices.\n"
            "- The 'forced to be free' passage appears to justify authoritarianism — the state can override any dissent in the name of the citizen's 'true' general will.\n"
            "- If the general will can diverge from all actual preferences, it is unclear who has the authority to identify it, opening the door to manipulation.\n"
            "- Rousseau's requirement that citizens share a common will seems to require cultural and economic homogeneity incompatible with modern pluralism.\n"
            "- Rousseau explicitly rejects individual rights as a check on sovereign power, which many find alarming."
        ),
    },
    {
        "query": "What objections have been raised against Rawls's difference principle?",
        "topic": "Liberalism",
        "grading_notes": (
            "- From the right (Nozick-style): enforcing the difference principle requires continuous redistribution that violates rights arising from just acquisition and voluntary transfer.\n"
            "- From the left: the principle is insufficiently egalitarian — it permits very large inequalities as long as they benefit the worst-off group.\n"
            "- Critics question whether maximin reasoning (behind the veil of ignorance) is rational rather than irrationally risk-averse.\n"
            "- Classical liberals question why equal distribution should be the default: there is no obvious reason inequality requires justification but equality does not.\n"
            "- Note: the corpus discusses these objections in the liberalism article; for Nozick's detailed Wilt Chamberlain argument the system lacks a full treatment — see out-of-scope questions below."
        ),
    },
    {
        "query": "What is Plato's objection to democracy and how do Mill and Rousseau respond?",
        "topic": "Representative Democracy",
        "grading_notes": (
            "- Plato objects that ordinary citizens lack the knowledge and virtue to make wise political decisions; rule by the ignorant is likely to produce bad outcomes.\n"
            "- Mill responds by advocating representative democracy (citizens are removed one step from direct policy-making) and, more controversially, by proposing plural votes for educated citizens.\n"
            "- Rousseau responds by insisting that civic education, economic equality, and limits on factionalism can cultivate the virtue needed for citizens to deliberate about the common good.\n"
            "- Both Mill and Rousseau accept part of Plato's challenge but deny it defeats democracy entirely.\n"
            "- The elite-theory response (Schumpeter) is more concessive: it accepts citizen ignorance but reframes democracy as a peaceful mechanism for replacing rulers rather than genuine self-governance."
        ),
    },
    {
        "query": "What are the main challenges to the reach of liberalism?",
        "topic": "Liberalism",
        "grading_notes": (
            "- Mill controversially argued that liberty as a principle does not apply to 'uncivilised' peoples; this has been widely criticised as imperialist.\n"
            "- Rawls argued in The Law of Peoples that liberal principles do not apply universally; 'decent hierarchical societies' need not be liberal, provided they respect basic human rights and are organised cooperatively.\n"
            "- Cosmopolitan critics respond that all persons have equal dignity and liberal principles must therefore apply universally.\n"
            "- The tension between state-centred liberalism and cosmopolitan liberalism also affects distributive justice: does the difference principle apply globally or only within states?\n"
            "- The question of liberal interaction with non-liberal groups also arises domestically (religious communities, cultural minorities) as well as internationally."
        ),
    },

    # ---------------------------------------------------------------
    # EDGE CASES
    # ---------------------------------------------------------------
    {
        "query": "Is liberalism good?",
        "topic": "Liberalism",
        "grading_notes": (
            "- The question is too vague to answer definitively; a good response identifies this and asks for clarification or offers to discuss specific arguments.\n"
            "- A correct response should note that 'good' is contested and that different liberal traditions make very different claims.\n"
            "- The system should not give a one-sided answer without acknowledging the normative complexity.\n"
            "- Ideally the response invites the student to specify which aspect they want to explore (e.g., negative vs. positive liberty, classical vs. new liberalism, reach of liberalism)."
        ),
    },
    {
        "query": "Didn't Rousseau say that private property is the source of all happiness?",
        "topic": "Rousseau",
        "grading_notes": (
            "- This is a false-premise question; Rousseau argued the opposite: private property is the source of inequality and conflict, not happiness.\n"
            "- The Discourse on Inequality traces how private property combined with amour propre and material interdependence generates endemic social conflict and oppression.\n"
            "- A correct response gently corrects the premise and explains Rousseau's actual view.\n"
            "- The system should not affirm the false premise."
        ),
    },

    # ---------------------------------------------------------------
    # OUT-OF-SCOPE — graceful degradation tests
    # Graded on whether the system redirects to covered material
    # without confabulating detailed accounts from training data.
    # ---------------------------------------------------------------
    {
        "query": "What is Aristotle's argument for natural slavery in the Politics?",
        "topic": "Ancient Political Philosophy",
        "grading_notes": (
            "- A correct response does not cover Aristotle's Politics in detail, since it is outside the course material.\n"
            "- The system should redirect the student toward a related covered topic (e.g., Plato's objection to democracy, or the course's treatment of political authority).\n"
            "- The system should not confabulate a detailed account of Aristotle's natural-slavery argument."
        ),
    },
    {
        "query": "What is Nozick's Wilt Chamberlain argument and how does it refute patterned theories of justice?",
        "topic": "Distributive Justice",
        "grading_notes": (
            "- A correct response does not reconstruct the Wilt Chamberlain argument in detail, since the course material does not cover Nozick's Anarchy, State, and Utopia.\n"
            "- The system may briefly note the idea (touched on in the liberalism material) that enforcing patterned distributions requires continuous interference with free exchanges.\n"
            "- The system should redirect the student to covered material such as Rawls's difference principle or the classical vs. new liberalism debate."
        ),
    },
    {
        "query": "How does Habermas's theory of communicative action relate to deliberative democracy?",
        "topic": "Contemporary Political Philosophy",
        "grading_notes": (
            "- A correct response does not provide a substantive account of Habermas's communicative action theory, since it is not covered in the course material.\n"
            "- The system should redirect the student toward related covered material such as non-instrumentalist justifications for democracy or the public-justification view mentioned in the democracy article.\n"
            "- The system should not confabulate Habermasian theory from training data."
        ),
    },
    {
        "query": "What is Hannah Arendt's account of the public realm in The Human Condition?",
        "topic": "Contemporary Political Philosophy",
        "grading_notes": (
            "- A correct response does not cover Arendt's account of the public realm, since The Human Condition is not in the course material.\n"
            "- The system should redirect the student toward a related covered topic (e.g., Mill on individuality, Rousseau on civic participation, or democratic participation).\n"
            "- The system should not generate content from training data about Arendt's vita activa or labour/work/action distinction."
        ),
    },
    {
        "query": "What is Kant's categorical imperative?",
        "topic": "Kantian Ethics",
        "grading_notes": (
            "- A correct response does not cover Kant's categorical imperative in detail, since Kantian ethics is not part of the course material.\n"
            "- The system should redirect the student toward a related covered topic (e.g., Mill's utilitarianism, the harm principle, or sanction utilitarianism).\n"
            "- The system should not generate an account of the categorical imperative from training data."
        ),
    },
]
