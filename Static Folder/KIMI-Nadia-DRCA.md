FIXED Act IS "Safety, Rehabilitation and Compensation (Defence-related Claims) Act 1988"
FIXED compilation date IS "21 April 2025"
FIXED commencement date IS "12 October 2017"
FIXED maximum compensation for death with wholly dependent dependants IS 400000
FIXED maximum compensation for death with partly dependent dependants IS 400000
FIXED weekly compensation for prescribed child IS 110
FIXED maximum funeral expenses IS 9000
FIXED normal weekly earnings cap percentage IS 150
FIXED minimum earnings base IS 202
FIXED additional amount for prescribed person IS 50
FIXED additional amount for prescribed child IS 25
FIXED compensation redemption threshold IS 50
FIXED lump sum redemption formula numerator IS 52
FIXED pension age reduction formula numerator IS 5
FIXED pension age reduction formula denominator IS 100
FIXED qualifying period for primary site brain cancer IS 5
FIXED qualifying period for primary site bladder cancer IS 15
FIXED qualifying period for primary site kidney cancer IS 15
FIXED qualifying period for primary non-Hodgkins lymphoma IS 15
FIXED qualifying period for primary leukemia IS 5
FIXED qualifying period for primary site breast cancer IS 10
FIXED qualifying period for primary site testicular cancer IS 10
FIXED qualifying period for multiple myeloma IS 15
FIXED qualifying period for primary site prostate cancer IS 15
FIXED qualifying period for primary site ureter cancer IS 15
FIXED qualifying period for primary site colorectal cancer IS 15
FIXED qualifying period for primary site oesophageal cancer IS 15
FIXED maximum permanent impairment compensation IS 80000
FIXED minimum permanent impairment percentage IS 10
FIXED minimum binaural hearing loss percentage IS 5
FIXED non-economic loss base amount IS 15000
FIXED household services weekly cap IS 200
FIXED attendant care services weekly cap IS 200
FIXED minimum journey distance for compensation IS 50
FIXED maximum age for prescribed child IS 25
FIXED minimum age for prescribed child IS 16

INPUT employee IS BOOLEAN
INPUT injury IS BOOLEAN
INPUT disease IS BOOLEAN
INPUT aggravation IS BOOLEAN
INPUT employment start date IS DATE
INPUT employment end date IS DATE
INPUT MRCA commencement date IS DATE
INPUT injury date IS DATE
INPUT death date IS DATE
INPUT dependants IS LIST
    ITEM wholly dependent
    ITEM partly dependent
    ITEM prescribed child
INPUT medical treatment IS BOOLEAN
INPUT treatment cost IS NUMBER
INPUT journey distance IS NUMBER
INPUT public transport used IS BOOLEAN
INPUT ambulance used IS BOOLEAN
INPUT normal weekly earnings IS NUMBER
INPUT actual earnings IS NUMBER
INPUT superannuation pension IS NUMBER
INPUT superannuation lump sum IS NUMBER
INPUT permanent impairment percentage IS NUMBER
INPUT hearing loss percentage IS NUMBER
INPUT household services required IS BOOLEAN
INPUT household services cost IS NUMBER
INPUT attendant care services required IS BOOLEAN
INPUT attendant care services cost IS NUMBER
INPUT catastrophic injury IS BOOLEAN
INPUT employee age IS NUMBER
INPUT pension age IS NUMBER
INPUT retirement date IS DATE
INPUT imprisonment IS BOOLEAN
INPUT compensation previously paid IS NUMBER
INPUT damages recovered IS NUMBER
INPUT State compensation recovered IS NUMBER
INPUT firefighter employment duration IS NUMBER
INPUT firefighter exposure IS BOOLEAN
INPUT cancer type IS TEXT
INPUT employee is member of Defence Force IS BOOLEAN
INPUT employee is member of ADF Cadets IS BOOLEAN
INPUT employee is declared person IS BOOLEAN
INPUT medical treatment paid by Commonwealth IS BOOLEAN
INPUT injury from medical treatment IS BOOLEAN
INPUT treatment provided before MRCA commencement IS BOOLEAN
INPUT treatment spans MRCA commencement IS BOOLEAN
INPUT claim made IS BOOLEAN
INTENT claim determined IS BOOLEAN
INTENT MRCC determined IS BOOLEAN
INTENT Comcare determined IS BOOLEAN
INTENT employee retired IS BOOLEAN
INTENT employee imprisoned IS BOOLEAN
INTENT employee reached pension age IS BOOLEAN
INTENT employee reached two years before pension age IS BOOLEAN

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 1 - Short title
# Original: This Act may be cited as the Safety, Rehabilitation and Compensation (Defence-related Claims) Act 1988.
Act IS "Safety, Rehabilitation and Compensation (Defence-related Claims) Act 1988"

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 2 - Commencement
# Original: The whole of this Act commences on 12 October 2017.
Act commencement date IS DATE IS 12/10/2017

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 3 - Application of Act
# Original: This Act extends to all places outside Australia, including the external Territories.
Act applies outside Australia IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 4AA - Application of this Act
# Original: This Act applies in relation to an injury that is not an ailment, or an aggravation of an injury that is not an ailment, suffered by an employee if the injury or aggravation arises out of, or in the course of, the employee’s employment as a member of the Defence Force; and the employment occurred on or after 1 December 1988 and before 1 July 2004.
injury covered by Act IS CALC (
    injury IS TRUE AND
    employment start date >= 01/12/1988 AND
    employment end date < 01/07/2004 AND
    employee is member of Defence Force IS TRUE
)
    NEEDS injury
    NEEDS employment start date
    NEEDS employment end date
    NEEDS employee is member of Defence Force

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 5 - Employees
# Original: employee means a member of the Defence Force.
employee IS TRUE
    AND employee is member of Defence Force IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 5A - Definition of injury
# Original: injury means a disease suffered by an employee; or an injury (other than a disease) suffered by an employee, that is a physical or mental injury arising out of, or in the course of, the employee’s employment; or an aggravation of a physical or mental injury (other than a disease) suffered by an employee, that is an aggravation that arose out of, or in the course of, that employment; but does not include a disease, injury or aggravation suffered as a result of reasonable administrative action taken in a reasonable manner in respect of the employee’s employment.
injury IS TRUE
    OR disease IS TRUE
    OR (
        injury IS TRUE AND
        injury arises out of or in course of employment IS TRUE
    )
    OR (
        aggravation IS TRUE AND
        aggravation arises out of or in course of employment IS TRUE
    )
    AND NOT injury from reasonable administrative action IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 5B - Definition of disease
# Original: disease means an ailment suffered by an employee; or an aggravation of such an ailment; that was contributed to, to a significant degree, by the employee’s employment by the Commonwealth.
disease IS TRUE
    AND ailment IS TRUE
    AND disease contributed to by employment IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 6 - Injury arising out of or in the course of employment
# Original: Without limiting the circumstances in which an injury to an employee may be treated as having arisen out of, or in the course of, his or her employment, an injury shall, for the purposes of this Act, be treated as having so arisen if it was sustained as a result of an act of violence that would not have occurred but for the employee’s employment or the performance by the employee of the duties or functions of his or her employment; or while the employee was at the employee’s place of work, for the purposes of that employment, or was temporarily absent from that place during an ordinary recess in that employment; or while the employee was temporarily absent from the employee’s place of work undertaking an activity associated with the employee’s employment; or at the direction or request of the Commonwealth; or while travelling for the purpose of that employment; or while at a place of education; or while travelling between the employee’s place of work and a place of education; or while at a place for the purpose of obtaining a medical certificate; or receiving medical treatment; or undergoing a rehabilitation program; or receiving a payment of compensation; or undergoing a medical examination; or receiving money due to the employee; or while travelling between the employee’s place of work and another place for such purposes; or while at a place outside Australia at the direction or request of the Commonwealth; or while a member of a class declared by the Minister.
injury arises out of or in course of employment IS TRUE
    OR injury from act of violence IS TRUE
    OR injury at place of work IS TRUE
    OR injury during ordinary recess IS TRUE
    OR injury during activity associated with employment IS TRUE
    OR injury while travelling for employment IS TRUE
    OR injury at place of education IS TRUE
    OR injury while travelling to place of education IS TRUE
    OR injury while obtaining medical certificate IS TRUE
    OR injury while receiving medical treatment IS TRUE
    OR injury while undergoing rehabilitation program IS TRUE
    OR injury while receiving compensation payment IS TRUE
    OR injury while undergoing medical examination IS TRUE
    OR injury while receiving money due IS TRUE
    OR injury while travelling for medical purposes IS TRUE
    OR injury while outside Australia at direction of Commonwealth IS TRUE
    OR injury while member of declared class IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 6A - Injury arising out of or in the course of employment—extended operation
# Original: If an employee received medical treatment paid for by the Commonwealth and as an unintended consequence of that treatment the person suffered an injury, the injury is taken to have arisen out of, or in the course of, the person’s employment.
injury from medical treatment IS TRUE
    AND medical treatment paid by Commonwealth IS TRUE
    AND injury from medical treatment unintended IS TRUE
    AND NOT injury first suffered on or after MRCA commencement IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 7 - Provisions relating to diseases
# Original: Where an employee has suffered from a disease of a kind specified by the Minister as related to employment of a kind specified, and the employee was engaged in employment of that kind before symptoms first became apparent, the employment is taken to have contributed to the contraction of the disease, unless the contrary is established.
disease presumed from employment IS TRUE
    AND disease specified by Minister IS TRUE
    AND employment kind specified by Minister IS TRUE
    AND employee engaged in employment before symptoms IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 8 - Normal weekly earnings
# Original: Normal weekly earnings are calculated based on average hours worked and rate of pay during the relevant period, including overtime if regularly worked, and adjusted for increases due to age, service, or increments.
normal weekly earnings IS CALC (
    (average weekly hours * average hourly rate) + average weekly allowances + (average overtime hours * average overtime rate)
)
    NEEDS average weekly hours
    NEEDS average hourly rate
    NEEDS average weekly allowances
    NEEDS average overtime hours
    NEEDS average overtime rate

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 9 - Relevant period
# Original: The relevant period is the latest 2 weeks before the injury date during which the employee was continuously employed, disregarding any part before a pay variation unless impractical.
relevant period IS CALC (
    latest 2 weeks before injury date during continuous employment
)
    NEEDS injury date
    NEEDS employment start date
    NEEDS pay variation date

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 10 - Recovery of damages
# Original: Damages are taken to have been recovered when the amount is paid to or for the benefit of the employee or dependant.
damages recovered IS TRUE
    AND amount paid to or for benefit of employee or dependant IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 11 - Liability of relevant authority
# Original: The liability of a relevant authority to pay compensation is to pay such amount as is determined by the MRCC to be payable under this Act.
liability to pay compensation IS TRUE
    AND MRCC determined amount payable IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 12 - Amounts of compensation
# Original: An amount of compensation payable under a provision of this Act is in addition to amounts paid or payable under any other provision of this Act in respect of the same injury.
compensation amount IS CALC (
    compensation under this provision + compensation under other provisions
)
    NEEDS compensation under this provision
    NEEDS compensation under other provisions

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 13 - Indexation—Consumer Price Index
# Original: Relevant amounts are indexed annually on 1 July based on the CPI factor calculated from the December quarter index numbers.
indexed amount IS CALC (
    previous amount * CPI factor
)
    NEEDS previous amount
    NEEDS CPI factor

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 13AA - Indexation—Wage Price Index
# Original: Relevant amounts are indexed annually on 1 July based on the Wage Price Index factor calculated from the December quarter index numbers.
indexed amount IS CALC (
    previous amount * WPI factor
)
    NEEDS previous amount
    NEEDS WPI factor

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 14 - Compensation for Injuries
# Original: The Commonwealth is liable to pay compensation in accordance with this Act in respect of an injury suffered by an employee if the injury results in death, incapacity for work, or impairment, and is not intentionally self-inflicted or caused by serious and wilful misconduct unless resulting in death or serious permanent impairment.
compensation for injury IS TRUE
    AND injury results in death OR incapacity OR impairment IS TRUE
    AND NOT injury intentionally self-inflicted IS TRUE
    AND NOT (injury from serious misconduct AND NOT (injury results in death OR serious permanent impairment)) IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 15 - Compensation for Loss of or Damage to Property
# Original: The Commonwealth is liable to pay compensation for loss or damage to property used by the employee arising out of and in the course of employment, equal to reasonable expenditure for replacement or repair, unless attributable to serious and wilful misconduct.
compensation for property loss IS CALC (
    reasonable replacement or repair cost
)
    NEEDS reasonable replacement or repair cost
    AND loss or damage arises out of and in course of employment IS TRUE
    AND NOT loss or damage from serious misconduct IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 16 - Compensation in Respect of Medical Expenses
# Original: The Commonwealth is liable to pay compensation for reasonable medical treatment costs, and for necessary journeys over 50 km or involving public transport/ambulance, and for transportation to hospital or mortuary.
compensation for medical expenses IS CALC (
    treatment cost + journey compensation + transport cost
)
    NEEDS treatment cost
    NEEDS journey compensation
    NEEDS transport cost
    AND medical treatment reasonable IS TRUE
    AND (journey distance > 50 OR public transport used IS TRUE OR ambulance used IS TRUE) IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 17 - Compensation for Injuries Resulting in Death
# Original: If an employee dies leaving dependants, compensation of $400,000 is payable for wholly dependent dependants, up to $400,000 for partly dependent dependants, and $110 per week for prescribed children.
compensation for death IS CALC (
    wholly dependent dependants ? 400000 :
    partly dependent dependants ? determined amount up to 400000 :
    prescribed child ? 110 * weeks eligible :
    0
)
    NEEDS dependants
    NEEDS prescribed child
    NEEDS weeks eligible

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 18 - Compensation in Respect of Funeral Expenses
# Original: The Commonwealth is liable to pay compensation for reasonable funeral expenses, up to $9,000 (indexed), to the person who paid or carried out the funeral.
compensation for funeral expenses IS CALC (
    MIN(reasonable funeral cost, 9000)
)
    NEEDS reasonable funeral cost

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 19 - Compensation for Injuries Resulting in Incapacity
# Original: Compensation for incapacity is the difference between normal weekly earnings and actual earnings, capped at 45 times normal weekly hours, then reduced percentage of NWE based on employment level.
compensation for incapacity IS CALC (
    weeks <= 45 * normal weekly hours ? normal weekly earnings - actual earnings :
    (actual earnings <= 0.25 * normal weekly earnings ? 0.80 :
     actual earnings <= 0.50 * normal weekly earnings ? 0.85 :
     actual earnings <= 0.75 * normal weekly earnings ? 0.90 :
     actual earnings < normal weekly earnings ? 0.95 :
     1.00) * normal weekly earnings - actual earnings
)
    NEEDS normal weekly earnings
    NEEDS actual earnings
    NEEDS weeks

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 20 - Compensation for Injuries Resulting in Incapacity Where Employee Receives a Superannuation Pension
# Original: Compensation is reduced by the superannuation pension amount plus 5% of normal weekly earnings.
compensation with superannuation pension IS CALC (
    compensation without superannuation - (superannuation pension + 0.05 * normal weekly earnings)
)
    NEEDS compensation without superannuation
    NEEDS superannuation pension
    NEEDS normal weekly earnings

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 21 - Compensation for Injuries Resulting in Incapacity Where Employee Receives a Lump Sum Benefit
# Original: Compensation is reduced by the weekly interest on the lump sum plus 5% of normal weekly earnings.
compensation with lump sum benefit IS CALC (
    compensation without lump sum - (weekly interest on lump sum + 0.05 * normal weekly earnings)
)
    NEEDS compensation without lump sum
    NEEDS weekly interest on lump sum
    NEEDS normal weekly earnings

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 21A - Compensation for Injuries Resulting in Incapacity if Employee Receives a Superannuation Pension and a Lump Sum Benefit
# Original: Compensation is reduced by the superannuation pension plus weekly interest on the lump sum plus 5% of normal weekly earnings.
compensation with pension and lump sum IS CALC (
    compensation without both - (superannuation pension + weekly interest on lump sum + 0.05 * normal weekly earnings)
)
    NEEDS compensation without both
    NEEDS superannuation pension
    NEEDS weekly interest on lump sum
    NEEDS normal weekly earnings

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 22 - Compensation Where Employee is Maintained in a Hospital
# Original: If an employee is maintained in a hospital for at least one year and has no dependants, compensation is determined by the MRCC between 50% and 100% of what would have been payable under sections 19–21A.
compensation for hospital maintenance IS CALC (
    MRCC determined amount between 0.5 and 1.0 * compensation under sections 19-21A
)
    NEEDS MRCC determined amount
    NEEDS compensation under sections 19-21A
    AND hospital maintenance >= 1 year IS TRUE
    AND no dependants IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 23 - Compensation for Incapacity Not Payable in Certain Cases
# Original: Compensation is not payable if the employee has reached pension age, or is imprisoned, or after a lump sum redemption determination.
compensation not payable IS TRUE
    OR employee reached pension age IS TRUE
    OR employee imprisoned IS TRUE
    OR lump sum redemption determination made IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 24 - Compensation for Injuries Resulting in Permanent Impairment
# Original: Compensation is payable for permanent impairment assessed under the approved Guide, up to $80,000, unless impairment is less than 10% (or 5% for hearing loss), with exceptions for fingers, toes, taste, smell.
compensation for permanent impairment IS CALC (
    (permanent impairment percentage >= 10 OR exception applies) ? permanent impairment percentage / 100 * 80000 :
    (hearing loss percentage >= 5) ? hearing loss percentage / 100 * 80000 :
    0
)
    NEEDS permanent impairment percentage
    NEEDS exception applies
    NEEDS hearing loss percentage

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 25 - Interim Payment of Compensation
# Original: Interim compensation may be paid if permanent impairment is at least 10% but final assessment not yet made, with final adjustment after final determination.
interim compensation IS CALC (
    permanent impairment percentage >= 10 AND final assessment not made ? permanent impairment percentage / 100 * 80000 :
    0
)
    NEEDS permanent impairment percentage
    NEEDS final assessment not made

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 26 - Payment of Compensation
# Original: Compensation must be paid within 30 days of assessment, or interest is payable at a rate specified by the Minister.
compensation payment due IS CALC (
    assessment date + 30 days
)
    NEEDS assessment date
interest payable IS TRUE
    AND compensation not paid within 30 days IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 27 - Compensation for Non-Economic Loss
# Original: Non-economic loss compensation is $15,000 multiplied by the sum of the permanent impairment percentage and the degree of non-economic loss assessed under the approved Guide.
compensation for non-economic loss IS CALC (
    15000 * (permanent impairment percentage + degree of non-economic loss percentage)
)
    NEEDS permanent impairment percentage
    NEEDS degree of non-economic loss percentage

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 28 - Approved Guide
# Original: The MRCC must prepare and maintain a Guide to the Assessment of the Degree of Permanent Impairment, approved by the Minister, binding on the MRCC and Administrative Review Tribunal.
approved Guide IS TRUE
    AND MRCC prepared Guide IS TRUE
    AND Minister approved Guide IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 29 - Compensation for Household and Attendant Care Services for Non-Catastrophic Injury
# Original: Compensation for reasonable household services is between 50% and $200 per week; for attendant care services, $200 per week or actual cost if less.
compensation for household services IS CALC (
    MIN(MAX(0.5 * household services cost, household services cost), 200)
)
    NEEDS household services cost
    AND household services required IS TRUE
    AND catastrophic injury IS FALSE
compensation for attendant care services IS CALC (
    MIN(attendant care services cost, 200)
)
    NEEDS attendant care services cost
    AND attendant care services required IS TRUE
    AND catastrophic injury IS FALSE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 29A - Compensation for Household and Attendant Care Services for Catastrophic Injury
# Original: For catastrophic injury, compensation for reasonable household and attendant care services is such amount per week as the MRCC considers reasonable.
compensation for catastrophic household services IS CALC (
    MRCC determined reasonable amount
)
    NEEDS MRCC determined reasonable amount
    AND household services required IS TRUE
    AND catastrophic injury IS TRUE
compensation for catastrophic attendant care services IS CALC (
    MRCC determined reasonable amount
)
    NEEDS MRCC determined reasonable amount
    AND attendant care services required IS TRUE
    AND catastrophic injury IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 30 - Redemption of Compensation
# Original: If weekly compensation is $50 or less and incapacity unlikely to change, the MRCC must redeem future payments as a lump sum calculated by a prescribed formula.
redemption of compensation IS TRUE
    AND weekly compensation <= 50 IS TRUE
    AND incapacity unlikely to change IS TRUE
lump sum redemption amount IS CALC (
    52 * weekly compensation * [(specified number + 1)^n - 1] / (specified number * [(specified number + 1)^n])
)
    NEEDS weekly compensation
    NEEDS specified number
    NEEDS n

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 31 - Recurrent Payments after Payment of Lump Sum
# Original: After a lump sum redemption, if incapacity continues and employee unable to engage in suitable employment, weekly compensation resumes at the rate that would have been payable minus the redeemed amount.
recurrent compensation after redemption IS CALC (
    compensation rate before redemption - redeemed weekly amount
)
    NEEDS compensation rate before redemption
    NEEDS redeemed weekly amount
    AND incapacity continues IS TRUE
    AND unable to engage in suitable employment IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 33 - Reduction of Compensation in Certain Cases
# Original: Compensation is reduced by any salary, wages, or pay paid by the Commonwealth or licensed corporation for the same period, excluding certain leave payments.
reduced compensation IS CALC (
    compensation before reduction - salary wages pay paid
)
    NEEDS compensation before reduction
    NEEDS salary wages pay paid
    AND NOT excluded leave payment IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 36 - Assessment of Capability of Undertaking Rehabilitation Program
# Original: The rehabilitation authority must arrange assessment of capability to undertake a rehabilitation program on request or in certain circumstances, and may require medical examination.
rehabilitation assessment required IS TRUE
    OR employee requested assessment IS TRUE
    OR employee in specified class IS TRUE
    AND employee suffers injury resulting in incapacity or impairment IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 37 - Provision of Rehabilitation Programs
# Original: The rehabilitation authority may determine that an employee should undertake a rehabilitation program, and must consider various factors including cost, improvement in employment opportunities, and employee’s attitude.
rehabilitation program required IS TRUE
    AND rehabilitation assessment completed IS TRUE
    AND MRCC considers program beneficial IS TRUE
    AND employee attitude considered IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 39 - Compensation Payable in Respect of Certain Alterations etc.
# Original: Compensation is payable for reasonable costs of alterations to residence or workplace, vehicle modifications, or aids and appliances, if reasonably required due to impairment.
compensation for alterations IS CALC (
    reasonable cost of alterations or modifications or aids
)
    NEEDS reasonable cost of alterations or modifications or aids
    AND alteration or modification or aid reasonably required IS TRUE
    AND impairment results from injury IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 40 - Duty to Provide Suitable Employment
# Original: The Commonwealth must take all reasonable steps to provide or assist in finding suitable employment for an employee who is undertaking or has completed a rehabilitation program.
duty to provide suitable employment IS TRUE
    AND employee undertaking or completed rehabilitation program IS TRUE
    AND Commonwealth must take reasonable steps IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 41B - Acute support package
# Original: The MRCC may grant an acute support package to employees or related persons under 65 who are experiencing or at risk of crisis, subject to criteria including eligibility for compensation and recency of death.
acute support package eligible IS TRUE
    OR (
        employee IS TRUE AND
        employee age < 65 AND
        eligible for compensation under Division 3 of Part II IS TRUE AND
        crisis or risk of crisis IS TRUE
    )
    OR (
        related person of employee IS TRUE AND
        employee age < 65 AND
        eligible for compensation under Division 3 of Part II IS TRUE AND
        crisis or risk of crisis IS TRUE
    )
    OR (
        spouse of deceased employee IS TRUE AND
        wholly or partly dependent at death IS TRUE AND
        age < 65 AND
        death <= 2 years ago AND
        death resulted from injury IS TRUE
    )
    OR (
        parent or step-parent of deceased employee IS TRUE AND
        death <= 2 years ago AND
        death resulted from injury IS TRUE AND
        parenting child of deceased employee IS TRUE AND
        child age < 18 AND
        crisis or risk of crisis IS TRUE
    )
    OR (
        spouse of employee IS TRUE AND
        age < 65 AND
        (ceased being spouse <= 12 months ago OR child under 18 lives with person) IS TRUE AND
        crisis or risk of crisis IS TRUE
    )

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 44 - Action for damages not to lie against Commonwealth etc. in certain cases
# Original: An action for damages does not lie against the Commonwealth or an employee in respect of an injury sustained in the course of employment, except as provided in sections 45 and 46.
action for damages barred IS TRUE
    AND injury sustained in course of employment IS TRUE
    AND NOT exception under section 45 IS TRUE
    AND NOT exception under section 46 IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 45 - Actions for damages—election by employees
# Original: An employee may elect to institute an action for damages for non-economic loss instead of receiving compensation under sections 24, 25, or 27, but damages are capped at $110,000.
election for damages IS TRUE
    AND employee elected damages IS TRUE
    AND damages capped at 110000 IS TRUE
    AND compensation under sections 24 25 27 not payable after election IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 46 - Notice of common law claims against third party
# Original: If a claim is made against a third party for damages, the employee or dependant must notify the MRCC in writing within 7 days of becoming aware of the claim.
notice of common law claim IS TRUE
    AND claim made against third party IS TRUE
    AND notice given to MRCC within 7 days IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 48 - Compensation not payable where damages recovered
# Original: If damages are recovered, compensation is not payable after the date of recovery, and the employee or dependant must repay the lesser of the compensation paid or the damages recovered.
compensation not payable after damages IS TRUE
    AND damages recovered IS TRUE
    AND repayment required IS TRUE
repayment amount IS CALC (
    MIN(compensation paid, damages recovered)
)
    NEEDS compensation paid
    NEEDS damages recovered

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 50 - Common law claims against third parties
# Original: The MRCC may make or take over a claim against a third party for damages, and any damages recovered must be paid to the Commonwealth after deducting compensation paid and costs.
MRCC may claim against third party IS TRUE
    AND compensation paid under Act IS TRUE
    AND third party liability apparent IS TRUE
    AND damages recovered paid to Commonwealth IS TRUE
    AND deduction of compensation and costs IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 52 - Compensation not payable both under Act and under award
# Original: A person cannot receive both compensation under this Act and benefits under an award for the same injury or property loss; must elect one, and election is irrevocable.
election between Act and award IS TRUE
    AND compensation under Act IS TRUE
    AND benefits under award IS TRUE
    AND election made IS TRUE
    AND election irrevocable IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 53 - Notice of injury or loss of or damage to property
# Original: Compensation is not payable unless notice in writing is given to the relevant authority as soon as practicable after the employee becomes aware of the injury or loss.
notice of injury IS TRUE
    AND notice in writing given IS TRUE
    AND notice given as soon as practicable IS TRUE
    AND employee aware of injury IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 54 - Claims for compensation
# Original: Compensation is not payable unless a claim is made in writing in the approved form and accompanied by a medical certificate, unless the claim is under section 16 or 17.
claim for compensation IS TRUE
    AND claim in writing IS TRUE
    AND claim in approved form IS TRUE
    AND (claim under section 16 OR claim under section 17 OR medical certificate provided) IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 57 - Power to require medical examination
# Original: The relevant authority may require the employee to undergo a medical examination by a nominated practitioner, and compensation is suspended if the employee refuses without reasonable excuse.
medical examination required IS TRUE
    AND relevant authority requires examination IS TRUE
    AND employee refuses without reasonable excuse IS TRUE
    AND compensation suspended until examination IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 60 - Interpretation
# Original: In Part VI, claimant means a person in respect of whom a determination is made, and determination means a determination, decision or requirement made under specified sections.
claimant IS TRUE
    AND person in respect of whom determination made IS TRUE
determination IS TRUE
    AND determination made under specified sections IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 61 - Determinations to be notified in writing
# Original: The determining authority must give written notice of the determination to the claimant, including reasons and information about review rights.
determination notified IS TRUE
    AND written notice given IS TRUE
    AND reasons included IS TRUE
    AND review rights information included IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 62 - Reconsideration and review of determinations etc.
# Original: Determinations may be reconsidered by the Commission or reviewed by the Board under Part 4 of Chapter 8 of the MRCA, and further reviewed by the Administrative Review Tribunal.
reconsideration and review available IS TRUE
    AND reconsideration by Commission IS TRUE
    OR review by Board under MRCA IS TRUE
    OR review by Administrative Review Tribunal IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 110 - Money paid to relevant authority for benefit of person
# Original: Money payable to a person under a legal disability is paid to the relevant authority for the benefit of the person, and may be invested or applied as the authority thinks fit.
money for legally disabled person IS TRUE
    AND person under legal disability IS TRUE
    AND money paid to relevant authority IS TRUE
    AND money applied for benefit of person IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 111 - Provisions applicable on death of beneficiary
# Original: If a person entitled to compensation dies before payment, the amount forms part of the estate, or if no claimants, is paid to the Commonwealth.
compensation on death IS CALC (
    estate exists ? paid to estate :
    no claimants ? paid to Commonwealth :
    0
)
    NEEDS estate exists
    NEEDS no claimants

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 112 - Assignment, set-off or attachment of compensation
# Original: Compensation is not assignable, not subject to set-off except as provided, and not subject to attachment except under specified laws.
compensation not assignable IS TRUE
compensation not subject to set-off IS TRUE
    AND except as provided in Act IS TRUE
compensation not subject to attachment IS TRUE
    AND except under specified laws IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 113 - Recovery of amounts due to the Commonwealth
# Original: Amounts due to the Commonwealth may be recovered from money or investments held for the benefit of the debtor.
recovery of amounts due IS TRUE
    AND amount due to Commonwealth IS TRUE
    AND money or investments held for debtor IS TRUE
    AND recovery permitted IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 114 - Recovery of overpayments
# Original: Overpayments of compensation may be recovered as a debt due to the Commonwealth, and may be deducted from future compensation payable.
overpayment recovery IS TRUE
    AND overpayment exists IS TRUE
    AND recovery as debt due IS TRUE
    OR deduction from future compensation IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 114A - Notice to the MRCC of retirement of employee
# Original: The appropriate officer must notify the MRCC in writing when an employee receiving compensation retires, including the date and superannuation scheme.
notice of retirement IS TRUE
    AND appropriate officer aware of retirement IS TRUE
    AND written notice to MRCC IS TRUE
    AND retirement date included IS TRUE
    AND superannuation scheme identified IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 114B - Recovery of overpayment to retired employee
# Original: If a retired employee may have been overpaid compensation, the MRCC may require the superannuation administrator to withhold payments and repay the overpayment.
overpayment recovery from retired employee IS TRUE
    AND employee retired IS TRUE
    AND overpayment possible IS TRUE
    AND MRCC notice to administrator IS TRUE
    AND administrator withholds payment IS TRUE
    AND overpayment repaid IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 114C - The MRCC may write off debt
# Original: The MRCC may write off a debt due to the Commonwealth, effective from the date of the decision or a specified date.
debt write off IS TRUE
    AND MRCC decides to write off IS TRUE
    AND decision in writing IS TRUE
    AND effective date specified IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 114D - The MRCC may waive debt
# Original: The MRCC may waive the Commonwealth’s right to recover a debt, in accordance with Ministerial directions.
debt waiver IS TRUE
    AND MRCC decides to waive IS TRUE
    AND in accordance with Ministerial directions IS TRUE
    AND waiver in writing IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 115 - Deduction of overpayments of repatriation pensions
# Original: Overpayments of repatriation pensions may be deducted from compensation payable under this Act.
repatriation pension overpayment deduction IS TRUE
    AND overpayment of repatriation pension IS TRUE
    AND deduction from compensation payable IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 116 - Employees on compensation leave
# Original: Employees on compensation leave are not entitled to paid leave except maternity leave, but sick and recreation leave accrue for the first 45 weeks, and long service leave accrues throughout.
compensation leave IS TRUE
    AND employee on compensation leave IS TRUE
    AND no paid leave except maternity leave IS TRUE
    AND sick leave accrues for first 45 weeks IS TRUE
    AND recreation leave accrues for first 45 weeks IS TRUE
    AND long service leave accrues throughout IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 118 - Double benefits
# Original: Compensation is not payable if State workers’ compensation is recovered for the same injury or property loss, and previously paid Commonwealth compensation may be recovered.
double benefits barred IS TRUE
    AND State workers compensation recovered IS TRUE
    AND same injury or property loss IS TRUE
    AND Commonwealth compensation recoverable IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 119 - Compensation where State compensation payable
# Original: Compensation is reduced by the amount of State compensation recovered, and any prior overpayment must be repaid to the Commonwealth.
compensation reduced by State compensation IS CALC (
    compensation otherwise payable - State compensation recovered
)
    NEEDS compensation otherwise payable
    NEEDS State compensation recovered
repayment of overpayment IS CALC (
    MIN(Commonwealth compensation paid, State compensation recovered)
)
    NEEDS Commonwealth compensation paid
    NEEDS State compensation recovered

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 120 - Notice of departure from Australia etc.
# Original: Persons receiving compensation for over 3 months must notify the MRCC before leaving Australia, and provide overseas address every 3 months.
notice of departure IS TRUE
    AND compensation paid > 3 months IS TRUE
    AND notice given before leaving Australia IS TRUE
    AND overseas address provided every 3 months IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 121B - Regulations modifying the operation of this Act
# Original: The regulations may modify the operation of this Act if necessary to prevent disadvantage to any person except the Commonwealth.
regulations may modify Act IS TRUE
    AND modification necessary IS TRUE
    AND to prevent disadvantage IS TRUE
    AND except to Commonwealth IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 122 - Regulations
# Original: The Governor-General may make regulations prescribing matters required or permitted by this Act, or necessary or convenient for carrying it out.
regulations may be made IS TRUE
    AND Governor-General makes regulations IS TRUE
    AND for matters required or permitted IS TRUE
    OR necessary or convenient IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 122A - Legislative rules
# Original: The MRCC may make legislative rules prescribing matters required or permitted, except for creating offences, powers of arrest, tax, or amending the Act.
legislative rules may be made IS TRUE
    AND MRCC makes legislative rules IS TRUE
    AND for matters required or permitted IS TRUE
    AND NOT creating offences IS TRUE
    AND NOT creating powers of arrest IS TRUE
    AND NOT imposing tax IS TRUE
    AND NOT amending the Act IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 123 - Interpretation
# Original: In Part X, former employee means a person who was receiving weekly payments under the 1971 Act immediately before the commencing day and had ceased to be an employee before that day.
former employee IS TRUE
    AND receiving weekly payments under 1971 Act IS TRUE
    AND immediately before commencing day IS TRUE
    AND ceased to be employee before commencing day IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 124 - Application of Act to pre-existing injuries
# Original: This Act applies to injuries suffered before the commencing day if compensation was payable under the 1912, 1930, or 1971 Acts, and the amount of compensation is the same as would have been payable under those Acts.
pre-existing injury covered IS TRUE
    AND injury suffered before commencing day IS TRUE
    AND compensation payable under previous Acts IS TRUE
    AND amount same as under previous Acts IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 131 - Former employees under 65 who are in receipt of superannuation benefits and are unable to engage in any work
# Original: Compensation is adjusted so that the combined benefit of compensation and superannuation is 95% of normal weekly earnings if total benefit was >= 95%, or 70% if < 95%, with minimum 70% after increases.
compensation for former employee with superannuation IS CALC (
    total benefit >= 95% of normal weekly earnings ? 95% of normal weekly earnings - superannuation amount :
    total benefit >= 70% of normal weekly earnings ? 1971 amount :
    70% of normal weekly earnings - superannuation amount
)
    NEEDS total benefit
    NEEDS normal weekly earnings
    NEEDS superannuation amount
    NEEDS 1971 amount
    AND former employee age < 65 IS TRUE
    AND unable to engage in any work IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 132 - Former employees under 65 who are not in receipt of superannuation benefits and are unable to engage in any work
# Original: Compensation is 95% of normal weekly earnings if 1971 amount was >= 95%, or the 1971 amount if >= 70%, or 70% if < 70%, with minimum 70% after increases.
compensation for former employee without superannuation IS CALC (
    1971 amount >= 95% of normal weekly earnings ? 95% of normal weekly earnings :
    1971 amount >= 70% of normal weekly earnings ? 1971 amount :
    70% of normal weekly earnings
)
    NEEDS 1971 amount
    NEEDS normal weekly earnings
    AND former employee age < 65 IS TRUE
    AND not in receipt of superannuation benefits IS TRUE
    AND unable to engage in any work IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 132A - Former employees under 65 who are capable of engaging in any work
# Original: Compensation is reduced by the greater of actual or potential earnings, based on sections 131 or 132 less earnings, or sections 20 or 19 less 5% of normal weekly earnings, whichever is greater.
compensation for capable former employee IS CALC (
    in receipt of superannuation ? MAX((compensation under section 131 - actual or potential earnings), (compensation under section 20)) :
    MAX((compensation under section 132 - actual or potential earnings), (compensation under section 19 - 0.05 * normal weekly earnings))
)
    NEEDS in receipt of superannuation
    NEEDS actual or potential earnings
    NEEDS normal weekly earnings
    AND former employee age < 65 IS TRUE
    AND capable of engaging in any work IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 133 - Minimum benefit payable
# Original: If the combined benefit or compensation is less than the minimum earnings, it must be increased to the minimum earnings.
minimum benefit payable IS CALC (
    combined benefit or compensation < minimum earnings ? minimum earnings :
    combined benefit or compensation
)
    NEEDS combined benefit or compensation
    NEEDS minimum earnings

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 134 - Reduction of compensation on reaching pension age
# Original: Compensation is reduced by 5% for each year the former employee was under pension age at the commencing day, calculated by a formula.
reduction on reaching pension age IS CALC (
    (5 * (pension age - age at commencing day) / 100) * weekly compensation
)
    NEEDS pension age
    NEEDS age at commencing day
    NEEDS weekly compensation

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 135 - Former employees 65 and over who are in receipt of superannuation benefits
# Original: Compensation is equal to the 1971 amount for former employees aged 65 or over in receipt of superannuation benefits.
compensation for over 65 with superannuation IS CALC (
    1971 amount
)
    NEEDS 1971 amount
    AND age >= 65 IS TRUE
    AND in receipt of superannuation benefits IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 136 - Former employees 65 and over who are not in receipt of superannuation benefits
# Original: Compensation is equal to the 1971 amount for former employees aged 65 or over not in receipt of superannuation benefits.
compensation for over 65 without superannuation IS CALC (
    1971 amount
)
    NEEDS 1971 amount
    AND age >= 65 IS TRUE
    AND not in receipt of superannuation benefits IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 137 - Redemption on request by former employee
# Original: If weekly compensation is $62.99 or less and incapacity unlikely to change, the MRCC must redeem future payments as a lump sum calculated by a formula.
redemption on request IS TRUE
    AND weekly compensation <= 62.99 IS TRUE
    AND incapacity unlikely to change IS TRUE
    AND former employee requests redemption IS TRUE
lump sum redemption on request IS CALC (
    formula based on weekly compensation, specified number, n, and life expectancy
)
    NEEDS weekly compensation
    NEEDS specified number
    NEEDS n
    NEEDS life expectancy

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 140 - Simplified outline of this Part
# Original: This Part confers on the MRCC the functions of determining and managing defence-related claims under this Act for defence service before the MRCA commencement date.
MRCC functions for defence-related claims IS TRUE
    AND determining claims IS TRUE
    AND managing claims IS TRUE
    AND defence service before MRCA commencement IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 141 - Definitions
# Original: defence-related claim means a claim under this Act in respect of an injury, loss, damage or death related to defence service before the MRCA commencement date.
defence-related claim IS TRUE
    AND claim under this Act IS TRUE
    AND injury loss damage or death IS TRUE
    AND related to defence service IS TRUE
    AND defence service before MRCA commencement IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 142 - Functions of MRCC
# Original: The MRCC must determine defence-related claims accurately and quickly, guided by equity and good conscience, without regard to technicalities or rules of evidence.
MRCC to determine claims IS TRUE
    AND accurately and quickly IS TRUE
    AND guided by equity and good conscience IS TRUE
    AND without regard to technicalities IS TRUE
    AND not bound by rules of evidence IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 144A - Persons entitled to treatment under other legislation not entitled to certain compensation
# Original: The MRCC is not liable to pay compensation for medical treatment if the employee is entitled to treatment under the MRCA, VEA, or other specified Acts, unless exceptional circumstances apply.
no compensation for treatment if entitled elsewhere IS TRUE
    AND entitled to treatment under MRCA or VEA IS TRUE
    AND NOT exceptional circumstances IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 144B - Treatment of certain defence-related injuries to be provided under the MRCA or the Veterans’ Entitlements Act 1986
# Original: If the MRCC accepts liability for a defence-related injury, the employee is entitled to treatment under the MRCA or VEA from 10 December 2013 or acceptance date, and compensation under section 16 is not payable.
entitlement to treatment under MRCA or VEA IS TRUE
    AND MRCC accepts liability IS TRUE
    AND defence-related injury IS TRUE
    AND from 10 December 2013 or acceptance date IS TRUE
    AND section 16 compensation not payable IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 144C - Exceptional circumstances determination
# Original: The MRCC may determine that section 144B does not apply if exceptional circumstances exist, and must notify the employee.
exceptional circumstances determination IS TRUE
    AND MRCC satisfied exceptional circumstances IS TRUE
    AND determination in writing IS TRUE
    AND employee notified within 7 days IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 145 - Relevant authority
# Original: For defence-related claims, the MRCC is the relevant authority, and the Commonwealth is liable for amounts due.
MRCC is relevant authority IS TRUE
    AND for defence-related claims IS TRUE
    AND Commonwealth liable for amounts due IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 149 - Directions by Minister
# Original: The Minister may give written directions to the MRCC on general matters, and the MRCC must comply.
Minister may give directions IS TRUE
    AND directions in writing IS TRUE
    AND on general matters IS TRUE
    AND MRCC must comply IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 151 - MRCC may obtain information etc.
# Original: The MRCC may require persons to provide information, documents, or attend to answer questions for the purposes of this Act, with penalties for non-compliance.
MRCC may require information IS TRUE
    AND requirement in writing IS TRUE
    AND for purposes of Act IS TRUE
    AND penalty for non-compliance IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 151AA - Self-incrimination
# Original: A person is not excused from giving information on grounds of self-incrimination, but the information is not admissible in evidence against the individual except for offences under the Criminal Code.
self-incrimination not an excuse IS TRUE
    AND information not admissible against individual IS TRUE
    AND except for Criminal Code offences IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 151A - Giving information
# Original: The MRCC may provide information obtained under this Act to specified persons for specified purposes, and recipients must not use or disclose it for other purposes.
MRCC may give information IS TRUE
    AND to specified persons IS TRUE
    AND for specified purposes IS TRUE
    AND recipient must not misuse IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 152 - Delegation
# Original: The MRCC may delegate its functions or powers to persons eligible under the MRCA, and the Chief of the Defence Force may delegate to eligible persons under the MRCA.
MRCC may delegate IS TRUE
    AND to eligible persons under MRCA IS TRUE
Chief of Defence Force may delegate IS TRUE
    AND to eligible persons under MRCA IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 154 - Settlements and determinations etc. under the 1912 Act, the 1930 Act or the 1971 Act
# Original: Settlements and determinations under previous Acts relating to defence service are taken to be determinations by the MRCC under this Part.
previous settlements and determinations IS TRUE
    AND under 1912 1930 or 1971 Acts IS TRUE
    AND relating to defence service IS TRUE
    AND taken to be MRCC determinations IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 157 - Application of certain provisions to Defence Department
# Original: Certain SRC Act provisions do not apply to the Defence Department for defence service on or after MRCA commencement, and past payments are validated.
SRC Act provisions do not apply IS TRUE
    AND to Defence Department IS TRUE
    AND for defence service on or after MRCA commencement IS TRUE
    AND past payments validated IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 160 - Appropriation
# Original: The Consolidated Revenue Fund is appropriated for paying compensation, treatment, and other amounts under this Act.
Consolidated Revenue Fund appropriated IS TRUE
    AND for compensation IS TRUE
    AND for treatment IS TRUE
    AND for other amounts under Act IS TRUE

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 161 - Annual report
# Original: The MRCC must give the Minister an annual report by 30 September each year, including particulars of Ministerial directions.
annual report required IS TRUE
    AND by 30 September each year IS TRUE
    AND including Ministerial directions IS TRUE