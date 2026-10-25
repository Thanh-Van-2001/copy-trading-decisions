"""Generate the spoken script for the slide deck, with the deck's own numbers.

A script typed by hand drifts from the slides the first time a number changes.
This reads numbers.tex and substitutes the same macros the deck prints, so the
two cannot disagree; if the pipeline is re-run, the script moves with it.

Written to be said out loud in twelve to fifteen minutes: one point per slide,
the number spoken only where it carries that point, and nothing said twice.
Everything that was explanation rather than argument has been moved into the
anticipated-questions section at the end, which is not spoken.

Usage: python or_journal/make_script.py
"""
import io
import re

SRC = "paper_or/numbers.tex"
OUT = "paper_or/slides_script_en.md"
OUT_VI = "paper_or/slides_script_vi.md"


def values() -> dict:
    txt = io.open(SRC, encoding="utf-8").read()
    v = {}
    for k, raw in re.findall(r"\\newcommand\{\\(n[A-Za-z]+)\}\{(.*)\}\s*$", txt, re.M):
        # ASCII hyphen: a spoken script needs no typographic minus, and
        # pdflatex refuses U+2212 under the default encoding
        s = raw.replace(r"\ensuremath{\mathrm{-}}", "-").replace(r"\%", "%")
        s = re.sub(r"\\[a-zA-Z]+|[{}$]", "", s)
        v[k] = s.strip()
    return v


SCRIPT = r"""# Speaking script --- "Screening beats ranking"

**Deck:** `slides_itor.pdf` (21 pages: title + 20 slides)
**Length:** 12--15 minutes at a normal pace.
**Audience:** a co-author who has not read the paper.

Numbers are generated from the same run record as the slides, so the script
cannot drift from them. Say the ones in **bold**. Everything else is in the
questions section at the end.

---

## 1 --- Title *(15 sec)*

Thank you. Joint work with Professor Chan, submitted to *International
Transactions in Operational Research* last week.

The question is simple: a copy-trading investor makes several decisions. Which
of them is actually worth his attention?

---

## 2 --- He chooses people, not assets *(45 sec)*

On a copy-trading platform you do not pick assets. You pick *traders*, and the
platform mirrors their positions into your account.

That changes three things. Your candidates **die** --- a trader can stop at any
moment. Their quality is estimated from very short histories, so any ranking is
mostly noise. And you pay on *their* turnover, not on anything you decided.

A portfolio problem whose assets quit, are hard to rank, and cost money to hold.

---

## 3 --- Five choices *(45 sec)*

The investor really makes five choices: whom to admit, how to rank them, how
many to hold, what to do when one stops, and how much capital each gets.

The literature covers each separately --- portfolio selection under estimation
error, manager persistence, studies of signal providers, control with switching
costs.

What is missing is all five priced *against each other*, on one panel, net of
cost. Without that, a reader assumes each matters about as much as the others.
On this venue they do not.

---

## 4 --- What we add *(45 sec)*

Five contributions.

We rank all five decisions by what each was worth, gross and net of cost. We
*solve* the maintenance problem rather than posing it. We measure the three
primitives the decision needs, on a frame that is not a league table of winners.
We turn two of our own stated limitations into measurements. And the pipeline is
released: every number comes from a recorded run, and a hand-typed number fails
the build.

---

## 5 --- The objective *(45 sec)*

The set-up. A screen admits candidates; the copier holds k of them equally
weighted; his weekly return is their average, minus cost charged on turnover.

Notice the delta term: one if the leader traded that week, zero if he had
stopped. A stopped leader earns nothing and costs nothing. That does real work
later.

The structural point is that the screen and the basket size are **not
separable**. Tightening the screen raises quality and shrinks the pool --- it
buys return and pays in diversification. So we measure them together.

---

## 6 --- The data *(45 sec)*

The frame is the venue's public address list: **{nFrameSize}** addresses,
sampled by decile, of which **{nFrameUsable}** have enough history.

The point to notice is that **{nFrameLosing}** of them have lost money over
their lifetime. This is deliberately not a leaderboard --- survivor databases
overstate both returns and lifespans.

The box on the right is a mistake we made and corrected: a sleeve is in one of
*three* states each week, not two. Traded and measured; stopped, so it earns and
costs nothing; or still holding but unmeasurable, in which case it carries no
weight at all. Collapsing those changed a conclusion.

---

## 7 --- The cost *(45 sec)*

Cost is the weakest input, and we handle it by refusing to pick a value.

We could measure the venue's own fee --- **{nFeeFills}** fills give
**{nFeePooled} basis points per side**. We cannot measure the copier's
*additional* cost: his fee tier versus the leader's, and the shortfall from
executing after him.

So every cost-dependent result is reported over a grid from zero to twenty basis
points. Across the pairs of screens we compare, the ordering holds at **every**
level in **{nCrossoverSameThroughout}** of them. That is stronger than a point
estimate.

---

## 8 --- Proposition 1 *(45 sec)*

Four propositions. The first: if you cannot tell candidates apart, the optimal
basket is simply as large as the screen allows. The two-dimensional problem
collapses to one dimension.

But look what dependence does. Because leaders move together, a random basket is
worth only about **{nDepNEff} independent bets** however large it grows. The
chart shows the measured curve flattening against exactly that ceiling.

Diversification runs out long before the basket does.

---

## 9 --- Proposition 2 *(45 sec)*

The second is about maintenance. The rule turns out to be a **band**, not a
ranking: re-rank weekly, but move only when the gap is wide enough to clear a
threshold.

That threshold has two halves that behave completely differently. The cost half
is divided by the expected weeks a sleeve still trades, so it shrinks on a long
horizon. The risk half is not.

Measured, the cost half is only **{nTheoryBandTwentysixBp} basis points a
week**. On any realistic horizon this band is a risk object, not a cost object.

---

## 10 --- Propositions 3 and 4 *(45 sec)*

Proposition 3: the advantage of acting rises strictly with the gap, so the
inaction region is a single *interval* --- one boundary, not a ranking.

Proposition 4 brackets that boundary between two things we measure. It comes out
far too wide to act on, which is why we go further.

One framing point worth a moment. People reach for a restless bandit here. It is
the wrong model: a copier sees **every** candidate's equity path whether or not
he copies him, so capital buys no information that watching would not. No
exploration value. What is left is impulse control with a switching cost.

---

## 11 --- Solving the boundary *(1 min)*

So we solve it. The one thing we did not want to assume was the distribution of
the weekly change in the gap --- so we draw it from the
{nSolvedInnovations} changes we actually measure.

Backward induction returns the boundary: **{nSolvedTwentysix} basis points a
week** at a twenty-six week horizon, falling to {nSolvedFour} at four weeks.

That last row is the check. At one week there is nothing left to wait for, so the
boundary must collapse to break-even --- and it does, to the grid's resolution.
The solver is checking itself.

Then the economics. The boundary is **{nSolvedTwentysix}** basis points. The gap
a swap would act on sits at **{nMarginLevel}**. The answer is unambiguous: do not
swap.

---

## 12 --- Leaders die *(30 sec)*

Now the three primitives.

Attrition, by Kaplan--Meier with censoring. The stopping hazard is
**{nAttritionHazardSix} a month**, so **{nAttritionAliveTwelveMonths}** are still
trading a year later.

Worth noting: stopping here is mostly *withdrawal*, not blow-up. This is the rate
at which a copier loses a leader, not the rate at which a strategy dies.

---

## 13 --- Past ranks future, barely *(30 sec)*

Signal. The rank correlation between past Sharpe ratio and what the sleeve earns
next is **{nIcTwentysixSharpe}**, against a zero-skill band of {nIcNullLow} to
{nIcNullHigh}. Real, and small.

The striking part: inside a set *already screened* on past performance, it
**reverses**, to {nScPastsharpeIc}. Screening and ordering are substitutes ---
the second uses up what the first already extracted.

---

## 14 --- What each decision was worth *(1 min)*

This is the central table. Five decision dates, baskets of twenty.

Ordering the whole venue by past Sharpe is worth
**{nPolicyRankGainOpenTwentyMean}** in net Sharpe ratio. Screening on account
size, **{nPolicyScreenGainBigTwentyMean}**.

And then the other three. Ordering *inside* an already screened set,
{nPolicyRankGainBigTwentyMean}. Holding twenty instead of five,
{nPolicySpreadGainOpenTwentyMean}. Replacing a leader who stops,
{nPolicyReplaceGainBigTwentyMean}.

Two of the five carry almost everything; three are worth close to nothing. An
investor optimising basket size or replacement policy is optimising something
that does not move.

---

## 15 --- Is it real? *(45 sec)*

Consecutive dates share half their weeks, so inference uses the three dates whose
windows do not overlap at all.

The size screen adds **{nPolicyDisjointScreenBigWeekly} basis points a week**, at
a t of **{nPolicyDisjointScreenBigT}**. Ordering the venue adds
{nPolicyDisjointRankOpenWeekly}, at {nPolicyDisjointRankOpenT}. So of the four,
one is strong and the others are not.

The analysis of variance says the same thing differently: the date gives an F of
**{nPolicyVarFDate}**, the rule gives **{nPolicyVarFRule}**. *When* you choose
explains a great deal. *Which rule* chose explains nothing we can detect.

---

## 16 --- Gross of cost, the screens change places *(45 sec)*

This is the result I find most interesting.

Net of cost the two screens look comparable. Gross of cost they swap --- and that
says what each is buying. Before cost the account screen earns
**{nPolicyDisjointScreenBigGrossWeekly} basis points a week**; the risk screen
earns {nPolicyDisjointScreenRiskGrossWeekly}.

So one picks leaders who *make more money*. The other picks leaders who *move
less* --- which raises a ratio without raising a return, then gives most of it
back when cost is charged. Invisible if you only report net.

---

## 17 --- Is it just market exposure? *(45 sec)*

An obvious objection: the sample period was a rising market. If the screened
basket simply carries more beta, we have measured exposure and called it skill.

We checked. The size-screened basket runs at a beta of **{nScreenBigBetaA}**
against **{nScreenBigBetaB}** for the pool it beats --- slightly *less* exposed,
not more. Its annual alpha is **{nScreenBigAlphaA}** against
{nScreenBigAlphaB}.

Where exposure does differ, it differs the way we already claimed: the risk
screen runs {nScreenRiskBetaDiff} below the pool, which is what choosing leaders
who move less looks like against the market.

---

## 18 --- The fifth choice *(45 sec)*

We fix the weights at one over k. Does that give anything up?

We tested three estimated weightings against equal weights. They are better on
the Sharpe ratio in {nWeightBetterSharpe} of {nWeightComparisons} comparisons,
and *worse* on compound growth in {nWeightWorseGrowth}.

The mechanism is visible: minimum variance holds only
{nWeightBigMinvarNames} of the twenty leaders and puts
**{nWeightBigMinvarMaxw}** on one. Concentration raises a ratio and lowers a
geometric mean.

The largest difference reaches only a t of {nWeightMaxAbsT}. So we do not claim weighting
matters --- we claim one over k gives up nothing we can measure.

---

## 19 --- What we will not claim *(45 sec)*

I want to be explicit about the limits, because they are much of why I think the
paper is worth publishing.

The decision surface was searched over **{nSurfaceCells} cells**, and a rule with
no edge at all reaches a Sharpe ratio of **{nMultNullMax}**. No cell is
identified --- we claim a direction, never a location.

After a search this size the literature proposes a t of about three, not two. We
apply that to ourselves: **one of our four differences clears it**.

The band width is not identified either. And it is one venue, over one rising
market.

---

## 20 --- Two limits turned into measurements *(45 sec)*

Two of those we could close, with a second snapshot of the venue.

First, survivorship: does an account that blows up get *delisted*, so our
survival curve never sees it? No. Of **{nSnapBelowAcctmin}** addresses below the
threshold, exactly **{nSnapBelowAcctminLeft}** left the list. A leader who blows
up stays in the frame at a value near zero.

Second, and this one is against us. **{nSnapAllIdle}** of matched accounts traded
*nothing* over that fortnight, and our turnover proxy charges them anyway --- a
median over-charge of **{nSnapUnscreenedExcessBp} basis points a week** in the
unscreened pool against {nSnapScreenedExcessBp} in the screened one. Since the
unscreened pool is the baseline, that *inflates* the comparison it is used in.
Which is exactly why we read that comparison gross.

---

## 21 --- Where it stands *(30 sec)*

With ITOR since the nineteenth of October; median time to first decision there is
about eight days.

Two places I would most value your reading. The related work does not yet connect
this to agent-based market modelling or the service-systems literature on
delegation --- your ground, and the natural way to seat it in this journal. And
external validity: one venue over one rising market is what a referee will press
on hardest.

The measurement is done. The framing is where a second pair of eyes pays.

Thank you --- happy to take questions.

---

## If you are asked *(not spoken)*

**Why Sharpe and not utility?** We report compound growth alongside it
throughout. They agree everywhere except on basket size --- and that
disagreement is itself a finding: enlarging a basket of leaders who trade
heavily buys variance reduction the Sharpe ratio rewards and growth does not.

**Why not just hold the index?** We benchmark against BTC and ETH, but only on
one window, and we state that as a limitation. It is the first thing we would add
in a revision.

**Is 26 weeks enough?** No, and we say so four separate times. That is why the
paper claims a *direction* for the screen and refuses to claim a location on the
surface or a width for the band.

**Isn't the cost assumption doing the work?** It cannot be. Every comparison is
reported at zero cost as well, and the ordering between screens holds at every
level of the grid in {nCrossoverSameThroughout} of the pairs we compare.

**How wide was the analytic bracket?** {nBracketTwentysixLow} to
{nBracketTwentysixHigh} basis points at twenty-six weeks --- useless on its own,
which is why we solved the recursion instead.

**Why three states and not two?** A week in which a leader still holds capital
but cannot be measured is not a flat week. Filling it with a zero invents a
return and still charges cost for it. That correction changed one of our
conclusions.

**What was the measured dependence?** Median pairwise correlation
{nDepMedian} over {nDepPairs} pairs; average covariance is {nDepCovRatio} of
average variance, which is where the {nDepNEff} independent bets comes from.
"""


SCRIPT_VI = r"""# Kịch bản thuyết trình --- "Screening beats ranking"

**Slide:** `slides_itor.pdf` (21 trang: tiêu đề + 20 slide)
**Thời lượng:** 12--15 phút ở nhịp nói bình thường.
**Người nghe:** đồng tác giả, chưa đọc bài.

Số liệu sinh từ cùng một run record với slide, nên kịch bản không thể lệch khỏi
slide. Những số **in đậm** là số cần nhấn; phần còn lại nằm ở mục hỏi đáp cuối.

---

## 1 --- Tiêu đề *(15 giây)*

Xin cảm ơn. Đây là công trình chung với Giáo sư Chan, vừa nộp cho tạp chí
*International Transactions in Operational Research* tuần trước.

Câu hỏi rất đơn giản: một nhà đầu tư copy trading phải ra nhiều quyết định.
Quyết định nào thực sự đáng để anh ta bỏ công?

---

## 2 --- Anh ta chọn người, không chọn tài sản *(45 giây)*

Trên một nền tảng copy trading, bạn không chọn tài sản. Bạn chọn *người giao
dịch*, và nền tảng sao chép vị thế của họ vào tài khoản bạn.

Điều đó làm thay đổi ba thứ. Ứng viên của bạn **chết** --- một trader có thể
dừng bất cứ lúc nào. Chất lượng của họ phải ước lượng từ lịch sử rất ngắn, nên
mọi bảng xếp hạng chủ yếu là nhiễu. Và bạn trả phí trên turnover của *họ*, không
phải trên quyết định của bạn.

Một bài toán danh mục mà tài sản tự bỏ đi, khó xếp hạng, và tốn tiền chỉ để giữ.

---

## 3 --- Năm lựa chọn *(45 giây)*

Nhà đầu tư thực ra có năm lựa chọn: nhận ai vào danh sách, xếp hạng họ thế nào,
giữ bao nhiêu người, làm gì khi một người dừng, và chia vốn cho mỗi người bao
nhiêu.

Văn liệu đã bàn từng cái một --- portfolio selection dưới sai số ước lượng, tính
bền của hiệu quả nhà quản lý, các nghiên cứu về signal provider, điều khiển có
chi phí chuyển đổi.

Thứ chưa có là cả năm được **định giá so với nhau**, trên cùng một panel, sau
chi phí. Thiếu nó, người đọc mặc nhiên cho rằng cái nào cũng quan trọng ngang
nhau. Trên sàn này thì không.

---

## 4 --- Chúng tôi đóng góp gì *(45 giây)*

Năm đóng góp.

Chúng tôi xếp hạng cả năm quyết định theo giá trị thực của từng cái, báo cáo cả
gross lẫn net. Chúng tôi **giải** bài toán bảo trì chứ không chỉ đặt ra nó.
Chúng tôi đo ba primitive mà quyết định này cần, trên một khung mẫu không phải
bảng vàng người thắng. Chúng tôi biến hai giới hạn do chính mình nêu thành phép
đo. Và pipeline được phát hành: mọi con số đều sinh từ một run record, số gõ tay
sẽ làm hỏng build.

---

## 5 --- Hàm mục tiêu *(45 giây)*

Phần thiết lập. Một screen nhận ứng viên vào; người copy giữ k người với trọng
số bằng nhau; lợi nhuận tuần của anh ta là trung bình của họ, trừ chi phí tính
trên turnover.

Chú ý số hạng delta: bằng một nếu leader có giao dịch tuần đó, bằng không nếu đã
dừng. Leader đã dừng thì không sinh lời và cũng không tốn phí. Chi tiết này còn
quay lại sau.

Điểm cấu trúc quan trọng là screen và kích thước rổ **không tách rời**. Siết
screen thì chất lượng tăng nhưng pool co lại --- nó mua lợi nhuận và trả bằng
mức đa dạng hoá. Nên phải đo chúng cùng nhau.

---

## 6 --- Dữ liệu *(45 giây)*

Khung mẫu là danh sách địa chỉ công khai của sàn: **{nFrameSize}** địa chỉ, lấy
mẫu theo decile, trong đó **{nFrameUsable}** có đủ lịch sử để dùng.

Điểm đáng chú ý là **{nFrameLosing}** trong số đó **lỗ** tính trọn đời. Đây cố
tình không phải bảng xếp hạng --- các cơ sở dữ liệu chỉ chứa người sống sót
thổi phồng cả lợi nhuận lẫn tuổi thọ.

Khung bên phải là một lỗi chúng tôi từng mắc và đã sửa: mỗi tuần một ống tay ở
một trong **ba** trạng thái, không phải hai. Có giao dịch và đo được; đã dừng
nên không lời không phí; hoặc vẫn còn vốn nhưng tuần đó không đo được, khi ấy nó
không mang trọng số nào cả. Gộp ba trạng thái lại đã làm đổi một kết luận.

---

## 7 --- Chi phí *(45 giây)*

Chi phí là đầu vào yếu nhất, và cách chúng tôi xử lý là **từ chối chọn một con
số**.

Thứ đo được là phí của chính sàn --- **{nFeeFills}** fill cho ra
**{nFeePooled} điểm cơ bản mỗi chiều**. Thứ không đo được là chi phí **tăng
thêm** của người copy: chênh bậc phí so với leader, và phần trượt giá do khớp
lệnh sau anh ta.

Nên mọi kết quả phụ thuộc chi phí đều báo cáo trên một lưới từ không tới hai
mươi điểm cơ bản. Trong các cặp screen chúng tôi so sánh, thứ tự giữ nguyên ở
**mọi** mức trong **{nCrossoverSameThroughout}** cặp. Đó là phát biểu mạnh hơn
một ước lượng điểm.

---

## 8 --- Mệnh đề 1 *(45 giây)*

Bốn mệnh đề. Mệnh đề đầu: nếu bạn không phân biệt được ứng viên, thì rổ tối ưu
đơn giản là lớn hết mức screen cho phép. Bài toán hai chiều sập về một chiều.

Nhưng hãy nhìn phụ thuộc làm gì. Vì các leader dao động cùng nhau, một rổ ngẫu
nhiên chỉ đáng khoảng **{nDepNEff} cược độc lập** dù có lớn tới đâu. Biểu đồ cho
thấy đường đo được phẳng ra đúng vào cái trần đó.

Đa dạng hoá cạn trước khi rổ cạn.

---

## 9 --- Mệnh đề 2 *(45 giây)*

Mệnh đề thứ hai về bảo trì. Quy tắc hoá ra là một **dải**, không phải một bảng
xếp hạng: vẫn xếp hạng lại hàng tuần, nhưng chỉ đổi khi khoảng cách đủ rộng để
vượt một ngưỡng.

Ngưỡng đó có hai nửa hành xử hoàn toàn khác nhau. Nửa chi phí bị **chia** cho số
tuần kỳ vọng mà ống tay còn giao dịch, nên nó co lại khi chân trời dài. Nửa rủi
ro thì không.

Đo được, nửa chi phí chỉ là **{nTheoryBandTwentysixBp} điểm cơ bản một tuần**.
Trên mọi chân trời thực tế, dải này là một đối tượng **rủi ro**, không phải đối
tượng chi phí.

---

## 10 --- Mệnh đề 3 và 4 *(45 giây)*

Mệnh đề 3: lợi ích của việc hành động tăng chặt theo khoảng cách, nên vùng bất
động là một **khoảng** duy nhất --- một biên, không phải một bảng xếp hạng.

Mệnh đề 4 kẹp biên đó giữa hai đại lượng chúng tôi đo được. Kết quả ra quá rộng
để hành động theo, nên chúng tôi đi tiếp một bước nữa.

Trước đó, một điểm về khung lý thuyết đáng dừng lại một chút. Nhiều người sẽ
nghĩ ngay tới restless bandit. Đó là mô hình sai: người copy **nhìn thấy** đường
vốn của mọi ứng viên bất kể có copy hay không, nên bỏ vốn vào một leader không
mua thêm thông tin nào mà việc đứng xem không có. Không có giá trị thăm dò. Thứ
còn lại là impulse control với chi phí chuyển đổi.

---

## 11 --- Giải biên bằng quy nạp lùi *(1 phút)*

Nên chúng tôi giải nó. Thứ duy nhất chúng tôi không muốn giả định là phân phối
của thay đổi khoảng cách hàng tuần --- nên chúng tôi rút nó từ
{nSolvedInnovations} thay đổi **đo được thật**.

Quy nạp lùi trả về chính cái biên: **{nSolvedTwentysix} điểm cơ bản một tuần** ở
chân trời hai mươi sáu tuần, giảm còn {nSolvedFour} ở bốn tuần.

Dòng cuối là phép kiểm. Ở một tuần thì không còn gì để chờ, nên biên bắt buộc
phải sập về giá trị hoà vốn --- và nó sập đúng, trong độ phân giải của lưới. Bộ
giải tự kiểm chính nó.

Rồi đến phần kinh tế học. Biên là **{nSolvedTwentysix}** điểm cơ bản. Khoảng
cách mà một lần đổi thực sự so sánh chỉ **{nMarginLevel}**. Câu trả lời rõ ràng:
đừng đổi.

---

## 12 --- Leader chết *(30 giây)*

Giờ tới ba primitive.

Tỷ lệ rời bỏ, bằng Kaplan--Meier có kiểm duyệt. Hazard dừng là
**{nAttritionHazardSix} một tháng**, nên **{nAttritionAliveTwelveMonths}** vẫn
còn giao dịch sau một năm.

Đáng nói: dừng ở đây chủ yếu là **rút vốn**, không phải cháy tài khoản. Nên đây
là tốc độ người copy **mất** một leader, không phải tốc độ một chiến lược chết.

---

## 13 --- Quá khứ dự báo tương lai, nhưng rất yếu *(30 giây)*

Tín hiệu. Tương quan hạng giữa Sharpe ratio quá khứ và thứ ống tay kiếm được sau
đó là **{nIcTwentysixSharpe}**, so với dải vô kỹ năng chỉ từ {nIcNullLow} tới
{nIcNullHigh}. Có thật, và nhỏ.

Phần đáng chú ý: bên trong một tập **đã được sàng** theo hiệu quả quá khứ, tương
quan **đảo dấu**, còn {nScPastsharpeIc}. Sàng lọc và xếp hạng là **thay thế**
nhau --- cái sau dùng nốt thứ cái trước đã rút ra.

---

## 14 --- Mỗi quyết định đáng bao nhiêu *(1 phút)*

Đây là bảng trung tâm. Năm mốc quyết định, rổ hai mươi người.

Xếp hạng toàn sàn theo Sharpe quá khứ đáng
**{nPolicyRankGainOpenTwentyMean}** net Sharpe. Sàng theo quy mô tài khoản,
**{nPolicyScreenGainBigTwentyMean}**.

Rồi tới ba cái còn lại. Xếp hạng **bên trong** tập đã sàng,
{nPolicyRankGainBigTwentyMean}. Giữ hai mươi thay vì năm,
{nPolicySpreadGainOpenTwentyMean}. Thay một leader đã dừng,
{nPolicyReplaceGainBigTwentyMean}.

Hai trong năm gánh gần như toàn bộ; ba cái còn lại gần như không đáng gì trên
cùng hàm mục tiêu. Nhà đầu tư đi tối ưu kích thước rổ hay chính sách thay người
là đang tối ưu một thứ không nhúc nhích.

---

## 15 --- Có thật không? *(45 giây)*

Các mốc liên tiếp dùng chung một nửa số tuần, nên suy luận chỉ dựa trên ba mốc
có cửa sổ **không chồng lấn**.

Sàng quy mô thêm **{nPolicyDisjointScreenBigWeekly} điểm cơ bản một tuần**, với
t bằng **{nPolicyDisjointScreenBigT}**. Xếp hạng toàn sàn thêm
{nPolicyDisjointRankOpenWeekly}, t bằng {nPolicyDisjointRankOpenT}. Vậy trong
bốn cái, một cái mạnh, còn lại thì không.

Phân tích phương sai nói cùng điều đó theo hướng khác: **mốc thời gian** cho F
bằng **{nPolicyVarFDate}**, còn **quy tắc** cho **{nPolicyVarFRule}**. *Khi nào*
bạn chọn giải thích rất nhiều. *Quy tắc nào* chọn thì gần như không giải thích
được gì.

---

## 16 --- Trước chi phí, hai screen đổi chỗ *(45 giây)*

Đây là kết quả tôi thấy thú vị nhất.

Sau chi phí, hai screen trông ngang nhau. Trước chi phí chúng **đổi chỗ** --- và
điều đó cho biết mỗi cái thực sự mua gì. Trước chi phí, screen theo quy mô kiếm
**{nPolicyDisjointScreenBigGrossWeekly} điểm cơ bản một tuần**; screen theo rủi
ro chỉ {nPolicyDisjointScreenRiskGrossWeekly}.

Vậy một cái chọn những leader **kiếm được nhiều tiền hơn**. Cái kia chọn những
leader **dao động ít hơn** --- thứ làm tăng tỷ lệ mà không làm tăng lợi nhuận,
rồi trả lại gần hết khi tính phí. Nhìn số net không thôi thì không thấy.

---

## 17 --- Có phải chỉ là phơi nhiễm thị trường? *(45 giây)*

Một phản biện hiển nhiên: giai đoạn mẫu là thị trường tăng. Nếu rổ đã sàng đơn
giản là mang nhiều beta hơn, thì chúng tôi đã đo beta và gọi nó là kỹ năng.

Chúng tôi đã kiểm. Rổ sàng theo quy mô chạy ở beta **{nScreenBigBetaA}**, so với
**{nScreenBigBetaB}** của rổ nó đánh bại --- tức là phơi nhiễm **ít hơn**, không
phải nhiều hơn. Và alpha năm của nó là **{nScreenBigAlphaA}** so với
{nScreenBigAlphaB}.

Chỗ nào phơi nhiễm có khác thật thì nó khác đúng theo hướng chúng tôi đã nói:
screen theo rủi ro chạy thấp hơn rổ chung {nScreenRiskBetaDiff} --- đúng cái mà
"chọn người dao động ít" trông như thế nào khi đối chiếu với thị trường.

---

## 18 --- Lựa chọn thứ năm *(45 giây)*

Chúng tôi cố định trọng số ở một phần k. Làm thế có mất gì không?

Chúng tôi đã thử ba cách đặt trọng số ước lượng, so với trọng số bằng nhau.
Chúng tốt hơn về Sharpe ratio ở {nWeightBetterSharpe} trong
{nWeightComparisons} phép so sánh, và **tệ hơn** về tăng trưởng kép ở
{nWeightWorseGrowth}.

Cơ chế nhìn thấy được: minimum variance chỉ giữ {nWeightBigMinvarNames} trong
hai mươi leader và dồn **{nWeightBigMinvarMaxw}** vào một người. Tập trung làm
tăng tỷ lệ và giảm trung bình hình học.

Chênh lệch lớn nhất cũng chỉ đạt t bằng {nWeightMaxAbsT}. Nên chúng tôi không khẳng định
trọng số quan trọng --- chúng tôi khẳng định một phần k **không mất gì đo được**.

---

## 19 --- Những điều chúng tôi không khẳng định *(45 giây)*

Tôi muốn nói rõ về các giới hạn, vì đó là phần lớn lý do tôi nghĩ bài này đáng
công bố.

Mặt quyết định đã được dò qua **{nSurfaceCells} ô**, và một quy tắc hoàn toàn vô
dụng vẫn đạt Sharpe ratio **{nMultNullMax}**. Không ô nào được định danh ---
chúng tôi khẳng định một **hướng**, không bao giờ khẳng định một **vị trí**.

Sau một cuộc dò quy mô như vậy, văn liệu đề xuất ngưỡng t khoảng ba, không phải
hai. Chúng tôi áp nó cho chính mình: **một trong bốn chênh lệch vượt được**.

Bề rộng dải cũng không định danh được. Và đây là một sàn, trong một thị trường
tăng.

---

## 20 --- Hai giới hạn biến thành phép đo *(45 giây)*

Hai trong số đó chúng tôi đóng lại được, bằng một ảnh chụp thứ hai của sàn.

Thứ nhất, về sống sót: tài khoản cháy có bị **xoá khỏi danh sách** không, khiến
đường survival của chúng tôi không bao giờ thấy nó? Không. Trong
**{nSnapBelowAcctmin}** địa chỉ nằm dưới ngưỡng, đúng
**{nSnapBelowAcctminLeft}** địa chỉ rời đi. Leader cháy vẫn ở lại trong khung
mẫu với giá trị gần bằng không.

Thứ hai, và cái này **bất lợi cho chúng tôi**. **{nSnapAllIdle}** số tài khoản
khớp được **không giao dịch gì** trong hai tuần đó, mà proxy turnover vẫn tính
phí: thu vượt trung vị **{nSnapUnscreenedExcessBp} điểm cơ bản một tuần** ở rổ
chưa sàng, so với {nSnapScreenedExcessBp} ở rổ đã sàng. Vì rổ chưa sàng chính là
đối chứng, điều đó **thổi phồng** đúng phép so sánh mà nó được dùng. Và đó chính
là lý do chúng tôi đọc phép so sánh đó ở mức gross.

---

## 21 --- Hiện trạng *(30 giây)*

Bài đang ở ITOR từ ngày mười chín tháng Mười; trung vị thời gian tới quyết định
đầu ở tạp chí đó khoảng tám ngày.

Hai chỗ tôi mong thầy đọc kỹ nhất. Phần related work chưa nối bài này với
agent-based market modelling hay văn liệu service systems về uỷ quyền --- đúng
sân của thầy, và là cách tự nhiên để đặt bài vào tạp chí này. Và tính tổng quát:
một sàn, một thị trường tăng, là chỗ referee sẽ ép mạnh nhất.

Phần đo lường đã xong. Phần khung là chỗ một cặp mắt thứ hai có giá trị.

Xin cảm ơn --- rất mong nhận câu hỏi.

---

## Nếu bị hỏi *(không nói ra)*

**Sao dùng Sharpe mà không dùng utility?** Chúng tôi báo cáo tăng trưởng kép
song song suốt bài. Hai thước đo đồng ý ở mọi chỗ trừ kích thước rổ --- và chính
sự bất đồng đó là một phát hiện: nới rổ gồm những leader giao dịch nhiều thì mua
được phần giảm phương sai mà Sharpe thưởng còn tăng trưởng thì không.

**Sao không chỉ giữ index?** Chúng tôi có benchmark BTC và ETH, nhưng chỉ trên
một cửa sổ, và điều đó được nêu là giới hạn. Đây là thứ đầu tiên sẽ bổ sung ở
vòng revision.

**26 tuần có đủ không?** Không, và chúng tôi nói điều đó bốn lần riêng biệt. Đó
chính là lý do bài khẳng định một **hướng** cho screen và từ chối khẳng định vị
trí trên mặt quyết định hay bề rộng của dải.

**Có phải giả định chi phí đang gánh kết quả không?** Không thể. Mọi phép so
sánh đều được báo cáo ở mức chi phí bằng không, và thứ tự giữa các screen giữ
nguyên ở mọi mức trên lưới trong {nCrossoverSameThroughout} cặp.

**Khoảng chặn giải tích rộng bao nhiêu?** Từ {nBracketTwentysixLow} tới
{nBracketTwentysixHigh} điểm cơ bản ở hai mươi sáu tuần --- vô dụng nếu đứng
riêng, nên chúng tôi mới giải thẳng phương trình quy nạp.

**Sao lại ba trạng thái mà không phải hai?** Một tuần mà leader vẫn còn vốn
nhưng không đo được thì không phải một tuần phẳng. Điền số không vào đó là bịa
ra một mức lợi nhuận và vẫn tính phí cho nó. Phép sửa này đã làm đổi một kết
luận.

**Phụ thuộc đo được bao nhiêu?** Tương quan cặp trung vị {nDepMedian} trên
{nDepPairs} cặp; hiệp phương sai trung bình bằng {nDepCovRatio} phương sai trung
bình, và đó là nguồn của con số {nDepNEff} cược độc lập.
"""


def main() -> int:
    v = values()
    used = set(re.findall(r"\{(n[A-Za-z]+)\}", SCRIPT + SCRIPT_VI))
    missing = sorted(used - set(v))
    if missing:
        print("macros not defined:", missing)
        return 1
    vi = dict(v, nCrossoverSameThroughout=v["nCrossoverSameThroughout"].replace(" of ", "/"))
    for script, out, cut, rate, val in ((SCRIPT, OUT, "## If you are asked", 140, v),
                                        (SCRIPT_VI, OUT_VI, "## Nếu bị hỏi", 175, vi)):
        text = re.sub(r"\{(n[A-Za-z]+)\}", lambda m: val[m.group(1)], script)
        io.open(out, "w", encoding="utf-8").write(text)
        spoken = text.split(cut)[0]
        n = len(re.sub(r"[#*`\-]", " ", spoken).split())
        print(f"wrote {out}: {n} spoken words, about {n / rate:.0f} minutes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
