FIXED Act IS "Safety, Rehabilitation and Compensation (Defence-related Claims) Act 1988"
FIXED compilation date IS 21/04/2025
FIXED MRCA commencement date IS 01/07/2004
FIXED CERCA commencement date IS 01/12/1988
FIXED SRC Act commencement IS 01/12/1988
FIXED dependant relationships AS LIST
    ITEM spouse
    ITEM parent
    ITEM step-parent
    ITEM father-in-law
    ITEM mother-in-law
    ITEM grandparent
    ITEM child
    ITEM stepchild
    ITEM grandchild
    ITEM sibling
    ITEM half-sibling
FIXED reasonable administrative actions AS LIST
    ITEM a reasonable appraisal of the employee's performance
    ITEM a reasonable counselling action
    ITEM a reasonable suspension action
    ITEM a reasonable disciplinary action
    ITEM anything reasonable done in connection with a reasonable administrative action
    ITEM anything reasonable done in connection with the employee's failure to obtain a promotion, reclassification, transfer or benefit
FIXED maximum funeral compensation IS 9000
FIXED maximum permanent impairment compensation IS 80000
FIXED minimum binaural hearing loss for compensation IS 5
FIXED minimum general impairment for compensation IS 10
FIXED compensation for death leaving dependants IS 400000
FIXED weekly compensation for prescribed child IS 110
FIXED compensation leave accrual weeks IS 45
FIXED pension age buffer years IS 2
FIXED maximum incapacity weeks before reduction IS 104
FIXED minimum earnings base IS 202
FIXED minimum earnings dependant add-on IS 50
FIXED minimum earnings child add-on IS 25
FIXED minimum earnings percentage IS 90
FIXED maximum compensation percentage IS 150
FIXED redemption threshold weekly IS 50
FIXED former employee redemption threshold IS 62.99
FIXED MRCA IS "Military Rehabilitation and Compensation Act 2004"
FIXED Defence Department IS "Department of Defence"
FIXED Chief of the Defence Force IS "Chief of the Defence Force"
FIXED 1912 Act IS "Commonwealth Workmen's Compensation Act 1912"
FIXED 1930 Act IS "Commonwealth Employees' Compensation Act 1930"
FIXED 1971 Act IS "Compensation (Commonwealth Government Employees) Act 1971"
FIXED State workers compensation IS "compensation recoverable under a law of a State or of a Territory, or of a foreign country, relating to workers' compensation"
FIXED fire-fighter cancers AS LIST
    ITEM primary site brain cancer
    ITEM primary site bladder cancer
    ITEM primary site kidney cancer
    ITEM primary non-Hodgkins lymphoma
    ITEM primary leukemia
    ITEM primary site breast cancer
    ITEM primary site testicular cancer
    ITEM multiple myeloma
    ITEM primary site prostate cancer
    ITEM primary site ureter cancer
    ITEM primary site colorectal cancer
    ITEM primary site oesophageal cancer

FIXED qualifying period for fire-fighter cancer AS LIST
    ITEM primary site brain cancer = 5
    ITEM primary site bladder cancer = 15
    ITEM primary site kidney cancer = 15
    ITEM primary non-Hodgkins lymphoma = 15
    ITEM primary leukemia = 5
    ITEM primary site breast cancer = 10
    ITEM primary site testicular cancer = 10
    ITEM multiple myeloma = 15
    ITEM primary site prostate cancer = 15
    ITEM primary site ureter cancer = 15
    ITEM primary site colorectal cancer = 15
    ITEM primary site oesophageal cancer = 15

FIXED CPI reference period IS "December quarter"
FIXED WPI reference period IS "December quarter"
# current Ministerial determination
FIXED redemption specified number IS 0.06
FIXED pension-age taper numerator IS 5
FIXED pension-age taper denominator IS 100

INPUT the person's relationship to the employee AS TEXT
INPUT the person stood in position of parent to employee AS BOOLEAN
INPUT the employee stood in position of parent to person AS BOOLEAN
INPUT the person was dependent on employee at date of death AS BOOLEAN
INPUT is a body corporate incorporated for a public purpose AS BOOLEAN
INPUT is incorporated under a law of the Commonwealth AS BOOLEAN
INPUT is incorporated under a law of a State or Territory AS BOOLEAN
INPUT the Commonwealth has a controlling interest AS BOOLEAN
INPUT a Territory has a controlling interest AS BOOLEAN
INPUT a body corporate has a controlling interest AS BOOLEAN
INPUT the body corporate is declared to which this Act applies AS BOOLEAN
INPUT a body corporate has a substantial interest AS BOOLEAN
INPUT the person is a child within the meaning of the Family Law Act 1975 AS BOOLEAN
INPUT the person is a de facto partner AS BOOLEAN
INPUT the person is recognised as spouse by custom AS BOOLEAN
INPUT the person is a member of the Aboriginal race of Australia AS BOOLEAN
INPUT the person is a descendant of indigenous inhabitants of the Torres Strait Islands AS BOOLEAN
INPUT the employee is under the influence of alcohol AS BOOLEAN
INPUT the employee is under the influence of a drug AS BOOLEAN
INPUT the drug is prescribed by a legally qualified medical practitioner AS BOOLEAN
INPUT the drug is prescribed by a dentist AS BOOLEAN
INPUT the drug is used in accordance with that prescription AS BOOLEAN
INPUT is a member of the Defence Force AS BOOLEAN
INPUT service history AS LIST
    ITEM enlistment date AS DATE
    ITEM discharge date AS DATE
    ITEM service type AS TEXT
INPUT Minister has made a declaration under subsection 5(3) AS BOOLEAN
INPUT Minister has made a declaration under subsection 5(4) AS BOOLEAN
INPUT employee has rendered operational service on or after Military Compensation Act 1994 commencement AS BOOLEAN
INPUT provision for pension is made by Part II of VEA AS BOOLEAN
INPUT employee has rendered service for which provision for pension is made by Part IV of VEA AS BOOLEAN
INPUT injury is a disease AS BOOLEAN
INPUT injury is a physical or mental injury AS BOOLEAN
INPUT injury is an aggravation AS BOOLEAN
INPUT injury arises out of or in the course of employment AS BOOLEAN
INPUT ailment is contributed to by employment to a significant degree AS BOOLEAN
INPUT injury sustained as result of act of violence AS BOOLEAN
INPUT act of violence would not have occurred but for employment AS BOOLEAN
INPUT injury sustained while at place of work AS BOOLEAN
INPUT injury sustained while temporarily absent from place of work AS BOOLEAN
INPUT injury sustained during ordinary recess in employment AS BOOLEAN
INPUT injury sustained as unintended consequence of medical treatment AS BOOLEAN
INPUT medical treatment was paid for by the Commonwealth AS BOOLEAN
INPUT medical treatment provided on or after CERCA commencement date AS BOOLEAN
INPUT CTPA section 8 does not apply to injury AS BOOLEAN
INPUT loss or damage resulted from an accident AS BOOLEAN
INPUT accident arose out of and in the course of employment AS BOOLEAN
INPUT injury was suffered as result of reasonable administrative action AS BOOLEAN
INPUT reasonable administrative action was taken in a reasonable manner AS BOOLEAN
INPUT employee made a wilful and false representation about a disease AS BOOLEAN
INPUT disease is of a kind specified by the Minister AS BOOLEAN
INPUT employee was engaged in specified kind of employment AS BOOLEAN
INPUT incidence of that disease among persons in such employment is significantly greater AS BOOLEAN
INPUT employee suffers a disease mentioned in the firefighter table AS BOOLEAN
INPUT employee was employed as a firefighter AS BOOLEAN
INPUT firefighter qualifying period for disease met AS BOOLEAN
INPUT employee was exposed to the hazards of a fire scene AS BOOLEAN
INPUT contrary is established for disease presumption AS BOOLEAN
INPUT injury results in death AS BOOLEAN
INPUT injury results in incapacity for work AS BOOLEAN
INPUT injury results in impairment AS BOOLEAN
INPUT injury was intentionally self inflicted AS BOOLEAN
INPUT injury was caused by the serious and wilful misconduct of the employee AS BOOLEAN
INPUT injury results in serious and permanent impairment AS BOOLEAN
INPUT employee deceased leaving dependants AS BOOLEAN
INPUT dependants were wholly dependent on employee AS BOOLEAN
INPUT dependants were partly dependent on employee AS BOOLEAN
INPUT prescribed child was wholly or mainly dependent on employee AS BOOLEAN
INPUT funeral cost amount paid AS NUMBER
INPUT charges ordinarily made for funerals in the place AS NUMBER
INPUT reasonable funeral cost AS NUMBER
INPUT employee is incapacitated for work AS BOOLEAN
INPUT normal weekly hours AS NUMBER
INPUT total hours incapacitated AS NUMBER
INPUT employee is employed during incapacity week AS BOOLEAN
INPUT percentage of normal weekly hours employed AS NUMBER
INPUT employee is able to earn in suitable employment per week AS NUMBER
INPUT employee earns from any employment per week AS NUMBER
INPUT employee receives a pension under a superannuation scheme AS BOOLEAN
INPUT employee has retired from employment AS BOOLEAN
INPUT superannuation amount of pension per week AS NUMBER
INPUT employee retired before 22 of Schedule 1 to the Safety Rehabilitation and Compensation and Other Legislation Amendment Act 2007 commenced AS BOOLEAN
INPUT superannuation contributions employee would have paid per week AS NUMBER
INPUT employee receives a lump sum benefit under a superannuation scheme AS BOOLEAN
INPUT superannuation amount in relation to lump sum AS NUMBER
INPUT interest rate specified for lump sum calculation AS NUMBER
INPUT employee has reached pension age AS BOOLEAN
INPUT employee suffered injury after reaching the age that is 2 years before pension age AS BOOLEAN
INPUT number of weeks of incapacity compensation paid AS NUMBER
INPUT impairment is permanent AS BOOLEAN
INPUT degree of permanent impairment AS NUMBER
INPUT impairment is a hearing loss AS BOOLEAN
INPUT binaural hearing loss percentage AS NUMBER
INPUT impairment is loss of finger AS BOOLEAN
INPUT impairment is loss of toe AS BOOLEAN
INPUT impairment is loss of sense of taste AS BOOLEAN
INPUT impairment is loss of sense of smell AS BOOLEAN
INPUT degree of non economic loss AS NUMBER
INPUT injury is a catastrophic injury AS BOOLEAN
INPUT employee obtains household services AS BOOLEAN
INPUT amount paid per week for household services AS NUMBER
INPUT employee obtains attendant care services AS BOOLEAN
INPUT amount paid per week for attendant care services AS NUMBER
INPUT NWE AS NUMBER
INPUT AE AS NUMBER
INPUT adjustment percentage AS NUMBER
INPUT base incapacity compensation AS NUMBER
INPUT weekly interest on lump sum AS NUMBER
INPUT reasonable amount for services AS NUMBER
INPUT damages recovered in an action for non economic loss AS BOOLEAN
INPUT employee recovered damages AS BOOLEAN
INPUT a claim for compensation is made in accordance with section 54 AS BOOLEAN
INPUT employee made an election to institute an action for damages AS BOOLEAN
INPUT Secretary has arranged for use of computer programs AS BOOLEAN
INPUT decision is about disease not contributed to AS BOOLEAN
INPUT decision is about injury not arising out of employment AS BOOLEAN
INPUT decision is about aggravation not arising out of employment AS BOOLEAN
INPUT MRCC has assessed capability for rehabilitation program AS BOOLEAN
INPUT MRCC has determined that employee should undertake program AS BOOLEAN
INPUT MRCC has provided or arranged for provision of rehabilitation program AS BOOLEAN
INPUT MRCC has determined that alteration is reasonably necessary AS BOOLEAN
INPUT MRCC has determined that equipment is reasonably necessary AS BOOLEAN
INPUT MRCC has determined that alteration or equipment is not available under other laws AS BOOLEAN
INPUT employer has been identified as suitable employer AS BOOLEAN
INPUT employer has offered suitable employment AS BOOLEAN
INPUT employee has accepted offer of suitable employment AS BOOLEAN
INPUT employee has been provided with a copy of the determination AS BOOLEAN
INPUT application for review of determination is made AS BOOLEAN
INPUT application for review is made within 28 days AS BOOLEAN
INPUT MRCC has complied with guidelines AS BOOLEAN
INPUT delegate has complied with guidelines AS BOOLEAN
INPUT MRCC has made a delegation AS BOOLEAN
INPUT delegate is eligible under MRCA AS BOOLEAN
INPUT delegation is made by resolution AS BOOLEAN
INPUT determination AS TEXT
INPUT written notice AS BOOLEAN
INPUT reconsideration request AS BOOLEAN
INPUT review request AS BOOLEAN
INPUT reconsideration outcome AS TEXT
INPUT review outcome AS TEXT
INPUT State workers compensation AS TEXT
INPUT employee recovers State workers compensation in respect of injury AS BOOLEAN
INPUT employee recovers State workers compensation in respect of loss of property AS BOOLEAN
INPUT employee recovers State workers compensation in respect of damage to property AS BOOLEAN
INPUT State workers compensation is recovered by dependant of deceased employee AS BOOLEAN
INPUT State workers compensation is for benefit of dependant of deceased employee AS BOOLEAN
INPUT compensation has been paid by Commonwealth under this Act to employee AS BOOLEAN
INPUT compensation has been paid by Commonwealth under this Act to dependant of deceased employee AS BOOLEAN
INPUT MRCC has received claim AS BOOLEAN
INPUT claimant refuses to give statutory declaration under subsection (3) AS BOOLEAN
INPUT claimant refuses without reasonable excuse AS BOOLEAN
INPUT claimant fails to give statutory declaration under subsection (3) AS BOOLEAN
INPUT claimant fails without reasonable excuse AS BOOLEAN
INPUT claimant's right to compensation is suspended under subsection (4) AS BOOLEAN
INPUT commencing day AS DATE

INPUT injury was suffered before commencing day AS BOOLEAN
INPUT injury existed before commencement of this Act AS BOOLEAN
INPUT payment was made under 1912 Act AS BOOLEAN
INPUT payment was made under 1930 Act AS BOOLEAN
INPUT payment was made under 1971 Act AS BOOLEAN
INPUT notice was given under 1912 Act AS BOOLEAN
INPUT notice was given under 1930 Act AS BOOLEAN
INPUT notice was given under 1971 Act AS BOOLEAN
INPUT claim was made under 1912 Act AS BOOLEAN
INPUT claim was made under 1930 Act AS BOOLEAN
INPUT claim was made under 1971 Act AS BOOLEAN
INPUT settlement was made under 1912 Act AS BOOLEAN
INPUT settlement was made under 1930 Act AS BOOLEAN
INPUT settlement was made under 1971 Act AS BOOLEAN
INPUT determination was made under 1912 Act AS BOOLEAN
INPUT determination was made under 1930 Act AS BOOLEAN
INPUT determination was made under 1971 Act AS BOOLEAN
INPUT liability existed under 1912 Act AS BOOLEAN
INPUT liability existed under 1930 Act AS BOOLEAN
INPUT liability existed under 1971 Act AS BOOLEAN
INPUT money was held under 1971 Act AS BOOLEAN
INPUT investments were held under 1971 Act AS BOOLEAN
INPUT former employee is under 65 years of age AS BOOLEAN
INPUT former employee is in receipt of superannuation benefits AS BOOLEAN
INPUT former employee is unable to engage in any work AS BOOLEAN
INPUT former employee is not in receipt of superannuation benefits AS BOOLEAN
INPUT former employee is capable of engaging in any work AS BOOLEAN
INPUT former employee reaches pension age AS BOOLEAN
INPUT former employee is 65 years or over AS BOOLEAN
INPUT former employee requests redemption AS BOOLEAN

INPUT claim is made by member of Defence Force AS BOOLEAN
INPUT claim is made by dependant of member of Defence Force AS BOOLEAN
INPUT claim relates to injury or death AS BOOLEAN
INPUT injury or death is defence-related AS BOOLEAN
INPUT injury is suffered by member of Defence Force AS BOOLEAN
INPUT employment is defence service AS BOOLEAN
INPUT death is of member of Defence Force AS BOOLEAN
INPUT death results from defence-related injury AS BOOLEAN
INPUT MRCC manages defence-related claims AS BOOLEAN
INPUT MRCC makes determinations in relation to defence-related claims AS BOOLEAN
INPUT MRCC provides information in relation to defence-related claims AS BOOLEAN
INPUT MRCC gives copies of defence-related claims to Defence Department AS BOOLEAN
INPUT MRCC gives copies of determinations to Defence Department AS BOOLEAN
INPUT MRCC gives copies of other documents to Defence Department AS BOOLEAN
INPUT Defence Department cooperates with MRCC in management of claims AS BOOLEAN
INPUT Defence Department provides information to MRCC AS BOOLEAN
INPUT person is entitled to treatment under MRCA AS BOOLEAN
INPUT person is entitled to treatment under Veterans' Entitlements Act 1986 AS BOOLEAN
INPUT treatment is provided under MRCA AS BOOLEAN
INPUT treatment is provided under Veterans' Entitlements Act 1986 AS BOOLEAN
INPUT MRCC makes determination in exceptional circumstances AS BOOLEAN
INPUT determination relates to treatment of defence-related injury AS BOOLEAN
INPUT determination relates to compensation for defence-related injury AS BOOLEAN
INPUT rehabilitation authority is responsible for rehabilitation of members of Defence Force AS BOOLEAN
INPUT rehabilitation authority is responsible for rehabilitation of dependants of members of Defence Force AS BOOLEAN
INPUT MRCC gives notice to Chief of the Defence Force AS BOOLEAN
INPUT notice relates to defence-related claims AS BOOLEAN
INPUT notice relates to determinations AS BOOLEAN
INPUT rehabilitation authority provides rehabilitation programs AS BOOLEAN
INPUT rehabilitation programs are for members of Defence Force AS BOOLEAN
INPUT rehabilitation programs are for dependants of members of Defence Force AS BOOLEAN
INPUT Minister may give directions to MRCC AS BOOLEAN
INPUT directions relate to defence-related claims AS BOOLEAN
INPUT directions relate to management of claims AS BOOLEAN
INPUT MRCC may obtain information from Defence Department AS BOOLEAN
INPUT MRCC may obtain information from other sources AS BOOLEAN
INPUT information relates to defence-related claims AS BOOLEAN
INPUT person is not required to incriminate themselves AS BOOLEAN
INPUT person is not required to admit liability AS BOOLEAN
INPUT person is not required to provide evidence against themselves AS BOOLEAN
INPUT person may give information to MRCC AS BOOLEAN
INPUT information may be used by MRCC AS BOOLEAN
INPUT MRCC may delegate functions to other persons AS BOOLEAN
INPUT delegation is in writing AS BOOLEAN
INPUT delegation is subject to conditions AS BOOLEAN
INPUT certain provisions of this Act apply to Defence Department AS BOOLEAN
INPUT provisions relate to management of defence-related claims AS BOOLEAN
INPUT provisions relate to treatment of defence-related injuries AS BOOLEAN
INPUT money is appropriated for purposes of this Part AS BOOLEAN
INPUT money is paid out of Consolidated Revenue Fund AS BOOLEAN
INPUT MRCC prepares annual report AS BOOLEAN
INPUT annual report relates to operation of this Part AS BOOLEAN
INPUT annual report is presented to Parliament AS BOOLEAN
INPUT endnotes provide information about this compilation AS BOOLEAN
INPUT endnotes include information about amending laws AS BOOLEAN
INPUT endnotes include amendment history of provisions AS BOOLEAN
INPUT abbreviations are used in this compilation AS BOOLEAN
INPUT abbreviations are explained in this endnote AS BOOLEAN
INPUT abbreviations include Act names and other terms AS BOOLEAN
INPUT legislation history shows when provisions were amended AS BOOLEAN
INPUT legislation history shows which Acts amended provisions AS BOOLEAN
INPUT legislation history shows when amendments commenced AS BOOLEAN
INPUT amendment history shows details of amendments AS BOOLEAN
INPUT amendment history shows which provisions were amended AS BOOLEAN
INPUT amendment history shows effect of amendments AS BOOLEAN

INPUT employee was employed as firefighter AS BOOLEAN
INPUT firefighter employment duration AS NUMBER
INPUT employee was exposed to hazards of fire scene AS BOOLEAN
INPUT cancer type AS TEXT
INPUT contrary is established for disease presumption AS BOOLEAN
INPUT CTPA section 8 does not apply AS BOOLEAN
INPUT delegate is eligible under MRCA AS BOOLEAN
INPUT delegation is by written instrument AS BOOLEAN
INPUT MRCC satisfied exceptional circumstances AS BOOLEAN
INPUT MRCC has given guidelines to rehabilitation authority AS BOOLEAN
INPUT MRCC has made delegation AS BOOLEAN
INPUT annual report is presented to Parliament AS BOOLEAN
INPUT money is appropriated for this Part AS BOOLEAN
INPUT annual report relates to operation of this Part AS BOOLEAN
INPUT endnotes provide information about compilation AS BOOLEAN
INPUT abbreviation key explains abbreviations AS BOOLEAN
INPUT legislation history shows amendment dates AS BOOLEAN
INPUT amendment history shows provision details AS BOOLEAN
INPUT redemption lump sum AS NUMBER
INPUT former employee redemption lump sum AS NUMBER
INPUT Act short title AS TEXT

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 1 - Short title
# Original: This Act may be cited as the Safety, Rehabilitation and Compensation (Defence-related Claims) Act 1988.
Act short title IS "Safety, Rehabilitation and Compensation (Defence-related Claims) Act 1988"

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 2 - Commencement
# Original: Each provision of this Act specified in column 1 of the table commences, or is taken to have commenced, in accordance with column 2 of the table... The whole of this Act commenced on 12 October 2017.
Act commenced on 12/10/2017

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 3 - Application of Act
# Original: This Act extends to all places outside Australia, including the external Territories.
Act extends to all places outside Australia

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 3A - Secretary may arrange for use of computer programs
# Original: The Secretary may arrange for the use, under the Secretary's control, of computer programs for any purposes for which the MRCC may, or must, under this Act... make a decision or determination...
Secretary may use computer programs
    AND Secretary has arranged for use of computer programs
    AND NOT decision is excluded from computer program use
        OR decision is about disease not contributed to
        OR decision is about injury not arising out of employment
        OR decision is about aggravation not arising out of employment

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 4 - Interpretation
# Original: "dependant, in relation to a deceased employee, means: (a) the spouse, parent, step-parent, father-in-law, mother-in-law, grandparent, child, stepchild, grandchild, sibling or half-sibling of the employee; or (b) a person in relation to whom the employee stood in the position of a parent or who stood in the position of a parent to the employee, being a person who was wholly or partly dependent on the employee at the date of the employee's death."
dependant
    OR dependant relationship type one
        AND the person's relationship to the employee IS IN LIST: dependant relationships
        AND the person was dependent on employee at date of death
    OR dependant relationship type two
        AND the person stood in position of parent to employee
        AND the person was dependent on employee at date of death
    OR dependant relationship type three
        AND the employee stood in position of parent to person
        AND the person was dependent on employee at date of death

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 4 - Interpretation
# Original: "spouse includes: (a) in relation to an employee or a deceased employee—a person who is, or immediately before the employee's death was, a de facto partner of the employee; and (b) in relation to an employee or a deceased employee who is or was a member of the Aboriginal race of Australia or a descendant of indigenous inhabitants of the Torres Strait Islands—a person who is or was recognised as the employee's husband, wife or spouse by the custom prevailing in the tribe or group to which the employee belongs or belonged."
spouse
    OR de facto partner condition
        AND the person is a de facto partner
    OR custom recognised spouse condition
        AND the person is a member of the Aboriginal race of Australia OR the person is a descendant of indigenous inhabitants of the Torres Strait Islands
        AND the person is recognised as spouse by custom

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 4 - Interpretation
# Original: "Commonwealth authority means: (a) a body corporate that is incorporated for a public purpose by a law of the Commonwealth, other than a body declared by the Minister, by legislative instrument, to be a body corporate to which this Act does not apply; or (b) a body corporate that is incorporated for a public purpose by a law of a Territory (other than a law of the Australian Capital Territory or the Northern Territory) and is declared by the Minister, by legislative instrument, to be a body corporate to which this Act applies; or (c) a body corporate: (i) that is incorporated under a law of the Commonwealth or a law in force in a State or Territory; and (ii) in which: (A) the Commonwealth has a controlling or substantial interest; or (B) a Territory (other than the Australian Capital Territory or the Northern Territory) or a body corporate referred to in paragraph (a) or (b) has a controlling interest; and (iii) that is declared by the Minister, by legislative instrument, to be a body corporate to which this Act applies; or (d) a body corporate: (i) in which a body corporate declared under paragraph (c) has a controlling interest; and (ii) that is declared by the Minister, by legislative instrument, to be a body corporate to which this Act applies."
Commonwealth authority
    OR Commonwealth authority scenario one
        AND is a body corporate incorporated for a public purpose
        AND is incorporated under a law of the Commonwealth
        AND NOT the body corporate is declared to which this Act does not apply
    OR Commonwealth authority scenario two
        AND is a body corporate incorporated for a public purpose
        AND is incorporated under a law of a Territory
        AND the body corporate is declared to which this Act applies
    OR Commonwealth authority scenario three
        AND is a body corporate
        AND is incorporated under a law of the Commonwealth OR is incorporated under a law of a State or Territory
        AND Commonwealth or Territory has interest
            AND the Commonwealth has a controlling interest OR a Territory has a controlling interest OR a body corporate has a substantial interest
        AND the body corporate is declared to which this Act applies
    OR Commonwealth authority scenario four
        AND is a body corporate
        AND a body corporate declared under paragraph c has a controlling interest
        AND the body corporate is declared to which this Act applies

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 4 - Interpretation
# Original: "For the purposes of this Act, an employee who is under the influence of alcohol or a drug (other than a drug prescribed for the employee by a legally qualified medical practitioner or dentist and used by the employee in accordance with that prescription) shall be taken to be guilty of serious and wilful misconduct."
serious and wilful misconduct
    AND the employee is under the influence of alcohol OR the employee is under the influence of a drug
    AND NOT prescribed drug condition
        AND the drug is prescribed by a legally qualified medical practitioner OR the drug is prescribed by a dentist
        AND the drug is used in accordance with that prescription

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 5 - Employees
# Original: "In this Act: employee means a member of the Defence Force."
employee
    AND is a member of the Defence Force

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 5 - Employees
# Original: "The Minister may, by legislative instrument, declare that persons specified in the declaration... are, for the purposes of this Act, taken to be members of the Defence Force..."
person taken to be a member of Defence Force under subsection 5(3)
    AND Minister has made a declaration under subsection 5(3)

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 5 - Employees
# Original: "The Minister may, by legislative instrument, declare that persons specified in the declaration... are, for the purposes of this Act, taken to be employed by the Commonwealth..."
person taken to be employed by Commonwealth under subsection 5(4)
    AND Minister has made a declaration under subsection 5(4)

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 5 - Employees
# Original: "Subject to subsections (7) and (8), this Act does not apply in relation to service of a member of the Defence Force in respect of which provision for the payment of pension is made by: (a) the Veterans' Entitlements Act 1986; or (b) the Papua New Guinea (Members of the Forces Benefits) Act 1957."
Act does not apply to VEA or PNG service
    AND provision for pension is made by Part II of VEA
    AND NOT employee has rendered operational service on or after Military Compensation Act 1994 commencement
    AND NOT employee has rendered service for which provision for pension is made by Part IV of VEA

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 5A - Definition of injury
# Original: "injury means: (a) a disease suffered by an employee; or (b) an injury (other than a disease) suffered by an employee, that is a physical or mental injury arising out of, or in the course of, the employee's employment; or (c) an aggravation of a physical or mental injury (other than a disease) suffered by an employee (whether or not that injury arose out of, or in the course of, the employee's employment), that is an aggravation that arose out of, or in the course of, that employment; but does not include a disease, injury or aggravation suffered as a result of reasonable administrative action taken in a reasonable manner in respect of the employee's employment."
injury
    AND injury type virtual node
        OR is a disease
            AND injury is a disease
        OR is a physical or mental injury
            AND injury is a physical or mental injury
            AND injury arises out of or in the course of employment
        OR is an aggravation of a physical or mental injury
            AND injury is an aggravation
            AND injury arises out of or in the course of employment
    AND NOT injury is from reasonable administrative action
        AND injury was suffered as result of reasonable administrative action
        AND reasonable administrative action was taken in a reasonable manner

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 5B - Definition of disease
# Original: "disease means: (a) an ailment suffered by an employee; or (b) an aggravation of such an ailment; that was contributed to, to a significant degree, by the employee's employment by the Commonwealth."
disease
    AND ailment or aggravation virtual
        AND injury is a disease OR injury is an aggravation
    AND ailment is contributed to by employment to a significant degree

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 6 - Injury arising out of or in the course of employment
# Original: "an injury shall, for the purposes of this Act, be treated as having so arisen if it was sustained: (a) as a result of an act of violence... (b) while the employee was at the employee's place of work... (c) while the employee was temporarily absent from the employee's place of work..."
injury treated as arising out of employment
    AND injury circumstances virtual node
        OR injury from act of violence virtual
            AND injury sustained as result of act of violence
            AND act of violence would not have occurred but for employment
        OR injury at place of work virtual
            AND injury sustained while at place of work
        OR injury during recess virtual
            AND injury sustained while temporarily absent from place of work
            AND injury sustained during ordinary recess in employment
        OR injury while travelling for employment
        OR injury at place of education
        OR injury while obtaining medical certificate
        OR injury while receiving medical treatment
        OR injury while undergoing rehabilitation program
        OR injury while receiving compensation payment
        OR injury while undergoing medical examination
        OR injury at place outside Australia declared by Minister
        OR injury while at place outside Australia as member of declared class
    AND NOT injury sustained while voluntarily submitting to abnormal risk

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 6A - Injury arising out of or in the course of employment—extended operation
# Original: "if... an employee... received medical treatment paid for by the Commonwealth; and as an unintended consequence of that treatment the person suffered or suffers an injury; the injury to the employee is taken to have arisen out of, or in the course of, the person's employment"
injury from medical treatment arose out of or in the course of employment
    AND injury sustained as unintended consequence of medical treatment
    AND medical treatment was paid for by the Commonwealth

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 7 - Provisions relating to diseases
# Original: "A disease suffered by an employee... shall not be taken to be an injury... if the employee has... made a wilful and false representation that he or she did not suffer, or had not previously suffered, from that disease."
disease is not an injury
    AND employee made a wilful and false representation about a disease

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 7 - Provisions relating to diseases
# Original: "the employment... shall, for the purposes of this Act, be taken to have contributed, to a significant degree, to the contraction of the disease, unless the contrary is established."
employment contributed to disease
    AND NOT contrary is established for disease presumption
    AND disease presumption conditions met
        OR disease is specified
            AND disease is of a kind specified by the Minister
            AND employee was engaged in specified kind of employment
        OR incidence is greater
            AND incidence of that disease among persons in such employment is significantly greater
        OR firefighter presumption
            AND employee suffers a disease mentioned in the firefighter table
            AND employee was employed as a firefighter
            AND firefighter qualifying period for disease met
            AND employee was exposed to the hazards of a fire scene

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 4AA - Application of this Act
# Original: "This Act applies... in relation to an injury that is not an ailment... if: (a) the injury... arises out of, or in the course of, the employee's employment... and (b) the employment occurred: (i) on or after... 1 December 1988; and (ii) before the MRCA commencement date... but not before and on or after, the MRCA commencement date."
Act applies to non-ailment injury
    AND injury arises out of or in the course of employment
    AND employment period is within CERCA to MRCA
        AND NOT ALL service ITERATE: LIST OF service history
            AND enlistment date >= CERCA commencement date
            AND discharge date < MRCA commencement date

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 4AA - Application of this Act
# Original: "This Act applies... in relation to an ailment... if: (a) the ailment... is contributed to, to a significant degree, by the employee's employment... and (b) the employment occurred: (i) on or after... 1 December 1988; and (ii) before the MRCA commencement date... but not before and on or after, the MRCA commencement date."
Act applies to ailment
    AND ailment is contributed to by employment to a significant degree
    AND employment period is within CERCA to MRCA
        AND NOT ALL service ITERATE: LIST OF service history
            AND enlistment date >= CERCA commencement date
            AND discharge date < MRCA commencement date

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 4AA - Application of this Act
# Original: "This Act applies... in relation to loss of, or damage to, property... if: (a) the loss or damage resulted from an accident that arose out of, and in the course of, the employee's employment... and (b) the employment occurred: (i) on or after... 1 December 1988; and (ii) before the MRCA commencement date."
Act applies to property loss or damage
    AND loss or damage resulted from an accident
    AND accident arose out of and in the course of employment
    AND employment period is within CERCA to MRCA
        AND NOT ALL service ITERATE: LIST OF service history
            AND enlistment date >= CERCA commencement date
            AND discharge date < MRCA commencement date

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 4AA - Application of this Act
# Original: "This Act applies... in relation to any injury suffered by an employee if: (a) the injury is suffered as an unintended consequence of medical treatment... that was paid for by the Commonwealth; and (b) the treatment was provided on or after... 1 December 1988; and (c) section 8 of the... CTPA 2004 does not apply..."
Act applies to unintended medical treatment injury
    AND injury sustained as unintended consequence of medical treatment
    AND medical treatment was paid for by the Commonwealth
    AND medical treatment provided on or after CERCA commencement date
    AND CTPA section 8 does not apply to injury

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 14 - Compensation for Injuries
# Original: "Subject to this Part, the Commonwealth is liable to pay compensation in accordance with this Act in respect of an injury suffered by an employee if the injury results in death, incapacity for work, or impairment. (2) Compensation is not payable in respect of an injury that is intentionally self-inflicted. (3) Compensation is not payable in respect of an injury that is caused by the serious and wilful misconduct of the employee but is not intentionally self-inflicted, unless the injury results in death, or serious and permanent impairment."
Commonwealth is liable to pay compensation for an injury
    AND virtualNode-Commonwealth is liable to pay compensation for an injury
        OR Act applies to injury or aggravation
        OR Act applies to ailment
        OR Act applies to property loss or damage
        OR Act applies to unintended medical treatment injury
    AND injury results in compensable outcome
        OR injury results in death
        OR injury results in incapacity for work
        OR injury results in impairment
    AND NOT compensation is excluded
        OR injury was intentionally self inflicted
        OR serious and wilful misconduct exclusion applies
            AND injury was caused by the serious and wilful misconduct of the employee
            AND NOT injury results in death
            AND NOT injury results in serious and permanent impairment

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 15 - Compensation for loss of or damage to property
# Original: "If: (a) an employee has an accident arising out of and in the course of his or her employment by the Commonwealth; and (b) the accident does not cause injury to the employee but results in the loss of, or damage to, property used by the employee; the Commonwealth is liable to pay compensation to the employee of an amount equal to the amount of the expenditure reasonably incurred by the employee in the necessary replacement or repair of the property."
compensation for property loss or damage
    AND accident arose out of and in the course of employment
    AND property lost or damaged IS TRUE
    AND NOT loss or damage from serious wilful misconduct

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 16 - Compensation in respect of medical expenses
# Original: "Where an employee suffers an injury, the Commonwealth is liable to pay, in respect of the cost of medical treatment obtained in relation to the injury (being treatment that it was reasonable for the employee to obtain in the circumstances), compensation of such amount as the MRCC determines is appropriate to that medical treatment."
compensation for medical treatment
    AND VirtualNode-compensation for medical treatment
        OR Act applies to injury or aggravation
        OR Act applies to ailment
        OR Act applies to unintended medical treatment injury
    AND medical treatment obtained
    AND medical treatment reasonable
    AND NOT employee entitled to treatment under MRCA or VEA unless exceptional circumstances

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 17 - Compensation for injuries resulting in death
# Original: "If the employee dies leaving dependants some or all of whom were... wholly dependent on the employee, the Commonwealth is liable to pay compensation in respect of the injury of $400,000... If... a prescribed child was... wholly or mainly dependent on the employee... the Commonwealth is liable to pay compensation at the rate of $110 a week..."
compensation for death IS CALC ((dependants were wholly dependent on employee = TRUE) ? compensation for death leaving dependants :(dependants were partly dependent on employee = TRUE) ? determined amount not exceeding compensation for death leaving dependants : 0)
    NEEDS Commonwealth is liable to pay compensation for an injury
    NEEDS injury results in death
    NEEDS employee deceased leaving dependants
    NEEDS dependants were wholly dependent on employee
    NEEDS dependants were partly dependent on employee
    NEEDS compensation for death leaving dependants
    WANTS determined amount not exceeding compensation for death leaving dependants

compensation for prescribed child IS CALC ((injury results in death = TRUE AND prescribed child was wholly or mainly dependent on employee = TRUE) ? weekly compensation for prescribed child : 0)
    NEEDS injury results in death
    NEEDS prescribed child was wholly or mainly dependent on employee
    NEEDS weekly compensation for prescribed child

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 18 - Compensation in respect of funeral expenses
# Original: "Where an injury to an employee results in death, the Commonwealth is liable to pay compensation in respect of the cost of the employee's funeral... The amount of compensation is the amount, not exceeding the amount determined in accordance with subsection (4), that the MRCC considers reasonable..."
compensation for funeral expenses IS CALC (MIN( reasonable funeral cost, maximum funeral compensation ))
    NEEDS reasonable funeral cost
    NEEDS maximum funeral compensation
    WANTS funeral cost amount paid
    WANTS charges ordinarily made for funerals in the place

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 19 - Compensation for injuries resulting in incapacity
# Original: "for each week that is a maximum-rate compensation week during which the employee is incapacitated, an amount of compensation worked out using the formula: NWE - AE... AE is the greater of the following amounts: (a) the amount per week (if any) that the employee is able to earn in suitable employment; (b) the amount per week (if any) that the employee earns from any employment... adjustment percentage is a percentage equal to..."
weekly incapacity compensation amount IS CALC ((Commonwealth is liable to pay compensation for an injury = TRUE AND employee is incapacitated for work = TRUE AND NOT employee has reached pension age unless recent injury exception applies) ?( (total hours incapacitated <= (compensation leave accrual weeks * normal weekly hours)) ? (NWE - AE) : ((adjustment percentage * NWE) - AE) ): 0)
    NEEDS Commonwealth is liable to pay compensation for an injury
    NEEDS employee is incapacitated for work
    NEEDS employee has reached pension age unless recent injury exception applies
    NEEDS total hours incapacitated
    NEEDS compensation leave accrual weeks
    NEEDS normal weekly hours
    NEEDS NWE
    NEEDS AE
    NEEDS adjustment percentage

AE IS CALC (MAX( employee is able to earn in suitable employment per week, employee earns from any employment per week ))
    NEEDS employee is able to earn in suitable employment per week
    NEEDS employee earns from any employment per week

adjustment percentage IS CALC ((employee is employed during incapacity week = FALSE) ? 0.75 :(percentage of normal weekly hours employed <= 25) ? 0.80 :(percentage of normal weekly hours employed > 25 AND percentage of normal weekly hours employed <= 50) ? 0.85 :(percentage of normal weekly hours employed > 50 AND percentage of normal weekly hours employed <= 75) ? 0.90 :(percentage of normal weekly hours employed > 75 AND percentage of normal weekly hours employed < 100) ? 0.95 :1.00)
    NEEDS employee is employed during incapacity week
    NEEDS percentage of normal weekly hours employed

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 20 - Compensation for injuries resulting in incapacity where employee receives a superannuation pension
# Original: "The amount of compensation is the amount worked out using this formula: Amount of compensation - ( Superannuation amount + 5% of the employee's normal weekly earnings)"
incapacity compensation with superannuation pension IS CALC ((employee retired before 22 of Schedule 1 to the Safety Rehabilitation and Compensation and Other Legislation Amendment Act 2007 commenced = TRUE) ?(base incapacity compensation - (superannuation amount of pension per week + superannuation contributions employee would have paid per week)) :(base incapacity compensation - (superannuation amount of pension per week + (0.05 * NWE))))
    NEEDS base incapacity compensation
    NEEDS superannuation amount of pension per week
    NEEDS NWE
    NEEDS employee retired before 22 of Schedule 1 to the Safety Rehabilitation and Compensation and Other Legislation Amendment Act 2007 commenced
    WANTS superannuation contributions employee would have paid per week

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 21 - Compensation for injuries resulting in incapacity where employee receives a lump sum benefit
# Original: "The amount of compensation is the amount worked out using this formula: Amount of compensation - ( Weekly interest on the lump sum + 5% of the employee's normal weekly earnings )... weekly interest on the lump sum means the amount worked out by: (a) multiplying the superannuation amount in relation to the lump sum benefit received by the employee by the rate specified... and (b) dividing the result of paragraph (a) by 52."
incapacity compensation with lump sum benefit IS CALC ((employee retired before 22 of Schedule 1 to the Safety Rehabilitation and Compensation and Other Legislation Amendment Act 2007 commenced = TRUE) ?(base incapacity compensation - (weekly interest on lump sum + superannuation contributions employee would have paid per week)) :(base incapacity compensation - (weekly interest on lump sum + (0.05 * NWE))))
    NEEDS base incapacity compensation
    NEEDS weekly interest on lump sum
    NEEDS NWE
    NEEDS employee retired before 22 of Schedule 1 to the Safety Rehabilitation and Compensation and Other Legislation Amendment Act 2007 commenced
    WANTS superannuation contributions employee would have paid per week

weekly interest on lump sum IS CALC ((superannuation amount in relation to lump sum * interest rate specified for lump sum calculation) / 52)
    NEEDS superannuation amount in relation to lump sum
    NEEDS interest rate specified for lump sum calculation

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 23 - Compensation for incapacity not payable in certain cases
# Original: "(1) Compensation is not payable... to an employee who has reached pension age. (1A) However, if an employee who has reached the age that is 2 years before pension age suffers an injury... compensation is payable... for a maximum of 104 weeks"
employee has reached pension age unless recent injury exception applies
    AND employee has reached pension age
    AND NOT recent injury exception applies
        AND employee suffered injury after reaching the age that is 2 years before pension age
        AND number of weeks of incapacity compensation paid < maximum incapacity weeks before reduction

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 24 - Compensation for injuries resulting in permanent impairment
# Original: "where an injury to an employee results in a permanent impairment, the Commonwealth is liable to pay compensation to the employee in respect of the injury... The amount assessed by the MRCC shall be an amount that is the same percentage of the maximum amount as the percentage determined by the MRCC..."
compensation for permanent impairment is payable
    AND Commonwealth is liable to pay compensation for an injury
    AND impairment is permanent
    AND NOT impairment compensation is excluded
        OR impairment is a hearing loss virtual
            AND impairment is a hearing loss = TRUE
            AND binaural hearing loss percentage < minimum binaural hearing loss for compensation
        OR impairment is not a hearing loss virtual
            AND impairment is a hearing loss = FALSE
            AND degree of permanent impairment < minimum general impairment for compensation
            AND NOT impairment is loss of finger
            AND NOT impairment is loss of toe
            AND NOT impairment is loss of sense of taste
            AND NOT impairment is loss of sense of smell

compensation amount for permanent impairment IS CALC ((degree of permanent impairment / 100) * maximum permanent impairment compensation)
    NEEDS degree of permanent impairment
    NEEDS maximum permanent impairment compensation

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 27 - Compensation for non-economic loss
# Original: "an amount of compensation is payable to the employee, in respect of the injury, for non-economic loss suffered by the employee... of an amount assessed by the MRCC under the formula..."
compensation for non economic loss IS CALC ((non economic loss base amount * (degree of permanent impairment / 100)) + (non economic loss base amount * (degree of non economic loss / 100)))
    NEEDS non economic loss base amount
    NEEDS degree of permanent impairment
    NEEDS degree of non economic loss

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 29 - Compensation for household services and attendant care services obtained as a result of a non-catastrophic injury
# Original: "where, as a result of an injury (other than a catastrophic injury) to an employee, the employee obtains household services that he or she reasonably requires, the Commonwealth is liable to pay compensation of such amount per week as the MRCC considers reasonable... being not less than 50% of the amount per week paid or payable by the employee for those services nor more than $200... Where, as a result of an injury (other than a catastrophic injury) to an employee, the employee obtains attendant care services... the Commonwealth is liable to pay compensation of: (a) $200 per week; or (b) an amount per week equal to the amount per week paid or payable by the employee for those services; whichever is less."
compensation for non catastrophic household services IS CALC (MAX( (0.5 * amount paid per week for household services), MIN( reasonable amount for services, household services non catastrophic max rate ) ))
    NEEDS reasonable amount for services
    NEEDS amount paid per week for household services
    NEEDS household services non catastrophic max rate

compensation for non catastrophic attendant care services IS CALC (MIN( attendant care services non catastrophic max rate, amount paid per week for attendant care services ))
    NEEDS attendant care services non catastrophic max rate
    NEEDS amount paid per week for attendant care services

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 29A - Compensation for household services and attendant care services obtained as a result of a catastrophic injury
# Original: "If, as a result of a catastrophic injury to an employee, the employee obtains household services that he or she reasonably requires, the Commonwealth is liable to pay compensation of such amount per week as the MRCC considers reasonable in the circumstances... If, as a result of a catastrophic injury to an employee, the employee obtains attendant care services that he or she reasonably requires, the Commonwealth is liable to pay compensation of such amount per week as the MRCC considers reasonable in the circumstances."
compensation for catastrophic household services IS CALC (reasonable amount for services)
    NEEDS reasonable amount for services

compensation for catastrophic attendant care services IS CALC (reasonable amount for services)
    NEEDS reasonable amount for services

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 30 - Redemption of compensation
# Original: If the weekly compensation payable to an employee is $50 or less, the MRCC must, if it is satisfied that the employee's incapacity is unlikely to change, redeem the weekly compensation by a lump sum payment.
weekly compensation is at redemption threshold
    AND weekly compensation <= redemption threshold weekly

MRCC satisfied incapacity unlikely to change
    AND MRCC satisfied that employee's incapacity is unlikely to change

number of days in redemption period
    OR employee injured before reaching age that is 2 years before pension age
        AND number of days = days from day after determination to day before employee reaches pension age
    OR employee injured on or after reaching age that is 2 years before pension age
        AND number of days virtual node
            OR number of days = days from day after determination to day before employee would cease to be entitled to receive compensation under section 19
            OR number of days = days from day after determination to day before employee would cease to be entitled to receive compensation under section 20
            OR number of days = days from day after determination to day before employee would cease to be entitled to receive compensation under section 21 
            OR number of days = days from day after determination to day before employee would cease to be entitled to receive compensation under section 21A

n IS CALC (number of days / 365)
    NEEDS number of days

amount per week conditions
    OR amount per week = weekly compensation payable under section 19 at date of determination
    OR amount per week = weekly compensation payable under section 20 at date of determination
    OR amount per week = weekly compensation payable under section 21 at date of determination
    OR amount per week = weekly compensation payable under section 21A at date of determination

redemption lump sum IS CALC ((52 * amount per week * ((redemption specified number + 1)^n - 1)) / (redemption specified number * ((redemption specified number + 1)^n)))
    NEEDS amount per week
    NEEDS redemption specified number
    NEEDS n

redemption of weekly compensation
    AND weekly compensation is at redemption threshold
    AND MRCC satisfied incapacity unlikely to change
    AND MRCC must redeem weekly compensation by lump sum payment
    AND redemption amount paid = redemption lump sum

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 30 - Redemption of compensation
# Original: If the weekly compensation payable to a former employee is $62.99 or less, the MRCC may, if it is satisfied that the former employee's incapacity is unlikely to change and the former employee requests redemption, redeem the weekly compensation by a lump sum payment.
former employee weekly compensation is at redemption threshold
    AND weekly compensation <= former employee redemption threshold

former employee MRCC satisfied incapacity unlikely to change
    AND MRCC satisfied that former employee's incapacity is unlikely to change

former employee requests redemption
    AND former employee requests redemption of weekly compensation

former employee number of days in redemption period
    OR former employee injured before reaching age that is 2 years before pension age
        AND number of days = days from day after determination to day before former employee reaches pension age
    OR former employee injured on or after reaching age that is 2 years before pension age
        AND number of days virtual node
            OR number of days = days from day after determination to day before employee would cease to be entitled to receive compensation under section 19
            OR number of days = days from day after determination to day before employee would cease to be entitled to receive compensation under section 20
            OR number of days = days from day after determination to day before employee would cease to be entitled to receive compensation under section 21
            OR number of days = days from day after determination to day before employee would cease to be entitled to receive compensation under section 21A

former employee n IS CALC (number of days / 365)
    NEEDS number of days

former employee amount per week
    AND amount per week virtual node
        OR amount per week = weekly compensation payable under section 19 at date of determination
        OR amount per week = weekly compensation payable under section 20 at date of determination
        OR amount per week = weekly compensation payable under section 21 at date of determination
        OR amount per week = weekly compensation payable under section 21A at date of determination

former employee redemption lump sum IS CALC ((52 * amount per week * ((redemption specified number + 1)^n - 1)) / (redemption specified number * ((redemption specified number + 1)^n)))
    NEEDS amount per week
    NEEDS redemption specified number
    NEEDS n

former employee redemption
    AND former employee weekly compensation is at redemption threshold
    AND former employee MRCC satisfied incapacity unlikely to change
    AND former employee requests redemption
    AND MRCC may redeem weekly compensation by lump sum payment
    AND former employee redemption amount paid = former employee redemption lump sum

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 36 - Assessment of capability of undertaking rehabilitation program
# Original: "The MRCC may, if it thinks it appropriate to do so, assess the capability of an employee to undertake a rehabilitation program... The MRCC may, by written notice given to the employee, require the employee to undergo an examination... by a person specified in the notice."
MRCC may assess capability for rehabilitation
    AND MRCC has assessed capability for rehabilitation program
    AND MRCC has determined that employee should undertake program

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 37 - Provision of rehabilitation programs
# Original: "If the MRCC has, under section 36, determined that an employee should undertake a rehabilitation program, the MRCC must, subject to this Part, provide or arrange for the provision of a rehabilitation program for the employee."
MRCC must provide rehabilitation program
    AND MRCC has assessed capability for rehabilitation program
    AND MRCC has determined that employee should undertake program
    AND MRCC has provided or arranged for provision of rehabilitation program

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 38 - Review of certain determinations by the MRCC
# Original: "An employee who is aggrieved by a determination of the MRCC under section 36 may apply to the MRCC for a review of the determination... An application for a review must be made within 28 days after the day on which the determination is given to the employee."
employee may apply for review of MRCC determination
    AND MRCC has assessed capability for rehabilitation program
    AND employee has been provided with a copy of the determination
    AND application for review of determination is made
    AND application for review is made within 28 days

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 39 - Compensation payable in respect of certain alterations etc.
# Original: "Where an employee suffers an injury resulting in an impairment and is undertaking, has completed a rehabilitation program (except under subsection 37(1A)), or has been assessed as not capable of such a program (except under subsection 36(1A)), the relevant authority shall pay reasonable compensation for costs of: (c) alteration of the employee's residence or workplace; (d) modifications of a vehicle or article used by the employee; or (e) aids or appliances for the employee, including repair or replacement. These must be reasonably required, having regard to the nature of the impairment and, where appropriate, the rehabilitation program."
employee suffers injury resulting in impairment
    AND employee suffers injury
    AND injury results in impairment

employee is undertaking rehabilitation program
    AND employee is undertaking rehabilitation program
    AND NOT rehabilitation program is under subsection 37(1A)

employee has completed rehabilitation program
    AND employee has completed rehabilitation program
    AND NOT rehabilitation program is under subsection 37(1A)

employee assessed as not capable of rehabilitation program
    AND employee has been assessed as not capable of rehabilitation program
    AND NOT assessment is under subsection 36(1A)

employee meets rehabilitation criteria virtual node
    OR employee is undertaking rehabilitation program
    OR employee has completed rehabilitation program
    OR employee assessed as not capable of rehabilitation program

alteration of residence reasonably required
    AND alteration of employee's residence is reasonably required
    AND alteration is reasonably required having regard to nature of impairment
    AND alteration is reasonably required having regard to rehabilitation program where appropriate

alteration of workplace reasonably required
    AND alteration of employee's workplace is reasonably required
    AND alteration is reasonably required having regard to nature of impairment
    AND alteration is reasonably required having regard to rehabilitation program where appropriate

alteration of residence or workplace reasonably required virtual node
    OR alteration of residence reasonably required
    OR alteration of workplace reasonably required

modifications of vehicle reasonably required
    AND modifications of vehicle used by employee is reasonably required
    AND modifications are reasonably required having regard to nature of impairment
    AND modifications are reasonably required having regard to rehabilitation program where appropriate

modifications of article reasonably required
    AND modifications of article used by employee is reasonably required
    AND modifications are reasonably required having regard to nature of impairment
    AND modifications are reasonably required having regard to rehabilitation program where appropriate

modifications of vehicle or article reasonably required virtual node
    OR modifications of vehicle reasonably required
    OR modifications of article reasonably required

aids or appliances reasonably required
    AND aids or appliances for employee are reasonably required
    AND aids or appliances are reasonably required having regard to nature of impairment
    AND aids or appliances are reasonably required having regard to rehabilitation program where appropriate

repair of aids or appliances reasonably required
    AND repair of aids or appliances is reasonably required
    AND repair is reasonably required having regard to nature of impairment
    AND repair is reasonably required having regard to rehabilitation program where appropriate

replacement of aids or appliances reasonably required
    AND replacement of aids or appliances is reasonably required
    AND replacement is reasonably required having regard to nature of impairment
    AND replacement is reasonably required having regard to rehabilitation program where appropriate

aids or appliances or repair or replacement reasonably required virtual node
    OR aids or appliances reasonably required
    OR repair of aids or appliances reasonably required
    OR replacement of aids or appliances reasonably required

alteration compensation scenario
    AND alteration of residence or workplace reasonably required virtual node
    AND relevant authority shall pay reasonable compensation for costs of alteration

modification compensation scenario
    AND modifications of vehicle or article reasonably required virtual node
    AND relevant authority shall pay reasonable compensation for costs of modifications

aids compensation scenario
    AND aids or appliances or repair or replacement reasonably required virtual node
    AND relevant authority shall pay reasonable compensation for costs of aids or appliances

compensation for alteration or equipment virtual node
    OR alteration compensation scenario
    OR modification compensation scenario
    OR aids compensation scenario

compensation for alteration or equipment
    AND employee suffers injury resulting in impairment
    AND employee meets rehabilitation criteria virtual node
    AND compensation for alteration or equipment virtual node
    AND relevant authority determines compensation amount

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 39 - Compensation payable in respect of certain alterations etc.
# Original: "The relevant authority shall consider the following when determining the compensation amount: (a) likely period the alteration, modification, or aid will be required; (b) difficulties in accessing or moving within the employee's residence or workplace; (c) difficulties in using a vehicle; (d) availability of alternative transport; (e) possibility of hiring the aid or appliance; (f) previous compensation received and whether disposal of the altered property increased its value."
relevant authority considers likely period alteration required
    AND relevant authority shall consider likely period alteration will be required

relevant authority considers likely period modification required
    AND relevant authority shall consider likely period modification will be required

relevant authority considers likely period aid required
    AND relevant authority shall consider likely period aid will be required

relevant authority considers likely period required virtual node
    OR relevant authority considers likely period alteration required
    OR relevant authority considers likely period modification required
    OR relevant authority considers likely period aid required

relevant authority considers access difficulties
    AND relevant authority shall consider difficulties in accessing employee's residence
    AND relevant authority shall consider difficulties in moving within employee's residence
    AND relevant authority shall consider difficulties in accessing employee's workplace
    AND relevant authority shall consider difficulties in moving within employee's workplace

relevant authority considers vehicle use difficulties
    AND relevant authority shall consider difficulties in using a vehicle

relevant authority considers alternative transport
    AND relevant authority shall consider availability of alternative transport

relevant authority considers hiring possibility
    AND relevant authority shall consider possibility of hiring the aid or appliance

relevant authority considers previous compensation
    AND relevant authority shall consider previous compensation received
    AND relevant authority shall consider whether disposal of altered property increased its value

relevant authority determines compensation amount
    AND relevant authority considers likely period required virtual node
    AND relevant authority considers access difficulties
    AND relevant authority considers vehicle use difficulties
    AND relevant authority considers alternative transport
    AND relevant authority considers hiring possibility
    AND relevant authority considers previous compensation

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 39 - Compensation payable in respect of certain alterations etc.
# Original: "Compensation is payable: (a) to the employee, or as directed; (b) if the employee dies before payment and another person paid the cost, to that person; (c) if unpaid and the employee/legal representative cannot claim, to the person to whom the cost is payable."
compensation payable to employee
    AND compensation is payable to employee

compensation payable as directed
    AND compensation is payable as directed by relevant authority

compensation payable to employee or as directed virtual node
    OR compensation payable to employee
    OR compensation payable as directed

compensation payable to person who paid cost after employee death
    AND employee dies before payment
    AND another person paid the cost
    AND compensation is payable to that person

employee cannot claim compensation
    AND employee cannot claim compensation

legal representative cannot claim compensation
    AND legal representative cannot claim compensation

person cannot claim compensation virtual node
    OR employee cannot claim compensation
    OR legal representative cannot claim compensation

compensation payable to person to whom cost is payable
    AND compensation is unpaid
    AND person cannot claim compensation virtual node
    AND compensation is payable to person to whom cost is payable

compensation payment determination virtual node
    OR compensation payable to employee or as directed virtual node
    OR compensation payable to person who paid cost after employee death
    OR compensation payable to person to whom cost is payable

compensation is paid
    AND compensation for alteration or equipment
    AND compensation payment determination virtual node

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 39 - Compensation payable in respect of certain alterations etc.
# Original: "Payment under subsection (3) discharges the liability of the person who initially incurred the cost."
payment discharges liability of person who incurred cost
    AND compensation is paid
    AND payment is made under subsection (3)
    AND payment discharges liability of person who initially incurred the cost

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 40 - Duty to provide suitable employment
# Original: "If the Commonwealth is liable to pay compensation... and the employee was a permanent employee of the Commonwealth on the day on which he or she was injured and continues to be so employed, the Commonwealth must, if it is reasonably practicable to do so, provide the employee with suitable employment... Suitable employment... means employment by the Commonwealth in work for which the employee is suited having regard to: (a) the employee's age, experience, training, language and other skills; (b) the employee's suitability for rehabilitation or vocational retraining; (c) where employment is available in a place that would require the employee to change his or her place of residence—whether it is reasonable to expect the employee to change his or her place of residence; and (d) any other relevant matter."
Commonwealth must provide suitable employment
    AND Commonwealth is liable to pay compensation for an injury
    AND employee was a permanent employee of the Commonwealth on the day on which he or she was injured
    AND employee continues to be employed by the Commonwealth
    AND it is reasonably practicable to provide suitable employment
    AND employer has been identified as suitable employer
    AND employer has offered suitable employment
    AND employee has accepted offer of suitable employment

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 40A - Scheme may provide for payments to employers
# Original: "A scheme made under the MRCA may provide for payments to employers of employees who are engaged in defence service... to encourage the provision of suitable employment to those employees."
scheme may provide for payments to employers
    AND scheme made under MRCA
    AND scheme provides for payments to employers
    AND employees are engaged in defence service
    AND payments are to encourage provision of suitable employment

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 41 - Rehabilitation authorities to comply with guidelines
# Original: "A rehabilitation authority must comply with any guidelines given to it by the MRCC."
rehabilitation authorities to comply with guidelines
    AND MRCC has given guidelines to rehabilitation authority
    AND rehabilitation authority must comply with guidelines

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 41A - Delegation by rehabilitation authority
# Original: "A rehabilitation authority may, by written instrument, delegate any of its powers or functions under this Part to a person who is eligible under the MRCA to be a member of the Board."
delegation by rehabilitation authority
    AND rehabilitation authority has made delegation
    AND delegation is by written instrument
    AND delegate is eligible under MRCA
    AND delegation is of powers or functions under this Part

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 41B - Acute support package
# Original: "If the MRCC is satisfied that a member of the Defence Force has suffered a catastrophic injury... the MRCC may, if it thinks it appropriate to do so, provide an acute support package to the member."
acute support package
    AND MRCC is satisfied that member has suffered catastrophic injury
    AND MRCC may provide acute support package
    AND MRCC thinks it appropriate to do so

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 42 - Interpretation
# Original: "In this Part, unless the contrary intention appears: action for non-economic loss means any action (whether or not it involves the formal institution of a proceeding) to recover an amount for damages for non-economic loss sustained by an employee as a result of an injury suffered by that employee..."
action for non-economic loss
    AND action is to recover damages for non-economic loss
    AND non-economic loss is sustained by employee
    AND non-economic loss is result of injury suffered by employee
    AND action is taken by employee against employer or another employee
    AND action follows election made by employee under subsection 45(1)

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 43 - Certain persons may request cessation of compensation payments
# Original: "A person who is receiving compensation under this Act may, at any time, request the MRCC to cease making the payments."
person may request cessation of compensation payments
    AND person is receiving compensation under this Act
    AND person may request MRCC to cease making payments

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 44 - Action for damages not to lie against Commonwealth etc. in certain cases
# Original: "An action for damages does not lie against the Commonwealth, a Commonwealth authority or a licensed corporation in respect of an injury to an employee if the employee has made an election under subsection 45(1) to institute an action for damages against a third party."
action for damages not to lie against Commonwealth
    AND action for damages is against Commonwealth or Commonwealth authority or licensed corporation
    AND action is in respect of injury to employee
    AND employee has made election under subsection 45(1) to institute action for damages against third party

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 45 - Actions for damages—election by employees
# Original: "An employee who has suffered an injury may elect to institute an action for damages against a third party... The election must be made in writing... The election must be made within 6 months after the day on which the injury occurred... The election must be given to the MRCC."
employee may elect to institute action for damages
    AND employee has suffered injury
    AND employee may elect to institute action for damages against third party
    AND election must be made in writing
    AND election must be made within 6 months after injury occurred
    AND election must be given to MRCC

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 46 - Notice of common law claims against third party
# Original: "An employee who has made an election under subsection 45(1) must give the MRCC written notice of any action for damages that the employee institutes against a third party."
notice of common law claims against third party
    AND employee has made election under subsection 45(1)
    AND employee must give MRCC written notice of action for damages
    AND action is against third party

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 47 - Notice of common law claims against Commonwealth
# Original: "An employee who has made an election under subsection 45(1) must give the MRCC written notice of any action for damages that the employee institutes against the Commonwealth."
notice of common law claims against Commonwealth
    AND employee has made election under subsection 45(1)
    AND employee must give MRCC written notice of action for damages
    AND action is against Commonwealth

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 48 - Compensation not payable where damages recovered
# Original: "If an employee has made an election under subsection 45(1) and recovers damages in respect of an injury, compensation is not payable under this Act in respect of that injury."
compensation not payable where damages recovered
    AND employee has made election under subsection 45(1)
    AND employee recovers damages in respect of injury
    AND compensation is not payable under this Act in respect of that injury

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 49 - Dependants not claiming compensation
# Original: "A dependant of a deceased employee may elect not to claim compensation under this Act in respect of the death of the employee."
dependant may elect not to claim compensation
    AND person is dependant of deceased employee
    AND dependant may elect not to claim compensation under this Act
    AND election is in respect of death of employee

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 50 - Common law claims against third parties
# Original: "An employee who has made an election under subsection 45(1) may institute an action for damages against a third party... The action may be instituted in any court of competent jurisdiction."
employee may institute action for damages against third party
    AND employee has made election under subsection 45(1)
    AND employee may institute action for damages against third party
    AND action may be instituted in any court of competent jurisdiction

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 51 - Payment of damages by persons to the Commonwealth
# Original: "If a person pays damages to an employee in respect of an injury, the employee must pay the amount of the damages to the Commonwealth."
payment of damages by persons to the Commonwealth
    AND person pays damages to employee in respect of injury
    AND employee must pay amount of damages to Commonwealth

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 52 - Compensation not payable both under Act and under award
# Original: "Compensation is not payable under this Act in respect of an injury if compensation is payable in respect of that injury under an award or order of an industrial court."
compensation not payable both under Act and under award
    AND compensation is payable under award or order of industrial court
    AND compensation is not payable under this Act in respect of that injury

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 52A - The Commonwealth's rights and obligations in respect of certain action for non-economic loss
# Original: "If an employee has made an election under subsection 45(1) and institutes an action for non-economic loss against a third party, the Commonwealth is liable to pay to the employee any amount that the employee is ordered to pay in costs to the third party."
Commonwealth liable to pay costs in action for non-economic loss
    AND employee has made election under subsection 45(1)
    AND employee institutes action for non-economic loss against third party
    AND Commonwealth is liable to pay to employee any amount ordered to pay in costs to third party

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 53 - Notice of injury or loss of, or damage to, property
# Original: "An employee who suffers an injury or the loss of, or damage to, property used by the employee must give written notice of the injury, loss or damage to the MRCC as soon as practicable after the injury, loss or damage occurs."
notice of injury or loss of or damage to property
    AND employee suffers injury or loss of or damage to property
    AND employee must give written notice to MRCC
    AND notice must be given as soon as practicable after injury loss or damage occurs

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 54 - Claims for compensation
# Original: "A claim for compensation must be made in accordance with this section."
claims for compensation
    AND claim for compensation must be made in accordance with section 54

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 55 - Survival of claims
# Original: "A claim for compensation survives the death of the claimant and may be pursued by the claimant's legal personal representative."
survival of claims
    AND claim for compensation survives death of claimant
    AND claim may be pursued by claimant's legal personal representative

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 56 - Claims may not be made in certain cases
# Original: "A claim for compensation may not be made in respect of an injury if the employee has made an election under subsection 45(1) to institute an action for damages against a third party."
claims may not be made in certain cases
    AND employee has made election under subsection 45(1) to institute action for damages against third party
    AND claim for compensation may not be made in respect of injury

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 57 - Power to require medical examination
# Original: "The MRCC may, by written notice given to an employee, require the employee to undergo a medical examination by a legally qualified medical practitioner specified in the notice."
power to require medical examination
    AND MRCC may require employee to undergo medical examination
    AND requirement is by written notice given to employee
    AND examination is by legally qualified medical practitioner specified in notice

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 58 - Power to request the provision of information
# Original: "The MRCC may, by written notice given to a person, require the person to give the MRCC any information that the MRCC reasonably requires for the purposes of this Act."
power to request provision of information
    AND MRCC may require person to give information
    AND requirement is by written notice given to person
    AND information is reasonably required for purposes of this Act

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 59 - Certain documents to be supplied on request
# Original: "A person who is required to give information to the MRCC under this Part must, if the MRCC so requires, give the MRCC any documents that are in the person's possession or control and that are relevant to the information."
certain documents to be supplied on request
    AND person is required to give information to MRCC under this Part
    AND MRCC requires person to give documents
    AND documents are in person's possession or control
    AND documents are relevant to the information

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part VI—Reconsideration and Review of Determinations
# Original: 60 Interpretation
interpretation
    AND determination = "decision made by the MRCC under this Act"

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part VI—Reconsideration and Review of Determinations
# Original: 61 Determinations to be notified in writing
determinations to be notified in writing
    AND written notice = TRUE
    AND NOT determination = NULL

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part VI—Reconsideration and Review of Determinations
# Original: 62 Reconsideration and review of determinations etc.
reconsideration and review of determinations
    OR reconsideration request = TRUE
        AND NOT reconsideration outcome = NULL
    OR review request = TRUE
        AND NOT review outcome = NULL

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 109A Jurisdiction of courts with respect to extraterritorial offences
jurisdiction of courts with respect to extraterritorial offences
    AND offence committed outside Australia
    AND offence is offence under this Act
    AND person is Australian citizen
    OR person is corporation incorporated in Australia

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 109 Determinations to be in writing
determinations to be in writing
    AND determination made by MRCC
    AND determination is in writing

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 110 Money paid to relevant authority for benefit of person
money paid to relevant authority for benefit of person
    AND money paid to Commonwealth
    AND money paid for benefit of person
    AND person is employee or former employee

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 111 Provisions applicable on death of beneficiary
provisions applicable on death of beneficiary
    AND beneficiary has died
    AND compensation is payable to beneficiary
    AND compensation becomes payable to legal personal representative

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 112 Assignment, set-off or attachment of compensation
assignment set-off or attachment of compensation
    AND compensation is payable under this Act
    AND NOT compensation is assigned
    AND NOT compensation is set-off
    AND NOT compensation is attached

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 112A Making of compensation payments through employers of employees paid out of relevant money
making of compensation payments through employers of employees paid out of relevant money
    AND employee is paid out of relevant money
    AND compensation is payable to employee
    AND compensation may be paid through employer

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 112B Making of compensation payments through employers of employees not paid out of relevant money
making of compensation payments through employers of employees not paid out of relevant money
    AND employee is not paid out of relevant money
    AND compensation is payable to employee
    AND compensation may be paid through employer

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 113 Recovery of amounts due to the Commonwealth
recovery of amounts due to the Commonwealth
    AND amount is due to Commonwealth
    AND Commonwealth may recover amount

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 114 Recovery of overpayments
recovery of overpayments
    AND overpayment has been made
    AND Commonwealth may recover overpayment

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 114A Notice to the MRCC of retirement of employee
notice to the MRCC of retirement of employee
    AND employee has retired
    AND notice is given to MRCC

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 114B Recovery of overpayment to retired employee
recovery of overpayment to retired employee
    AND employee has retired
    AND overpayment has been made to employee
    AND Commonwealth may recover overpayment

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 114C The MRCC may write off debt
the MRCC may write off debt
    AND debt is owed to Commonwealth
    AND MRCC may write off debt

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 114D The MRCC may waive debt
the MRCC may waive debt
    AND debt is owed to Commonwealth
    AND MRCC may waive debt

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 115 Deduction of overpayments of repatriation pensions
deduction of overpayments of repatriation pensions
    AND overpayment of repatriation pension has been made
    AND Commonwealth may deduct overpayment from compensation

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 116 Employees on compensation leave
employees on compensation leave
    AND employee is on compensation leave
    AND employee is absent from employment due to incapacity

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 118 Double benefits

employee recovers State workers compensation
    OR employee recovers State compensation for injury
    OR employee recovers State compensation for property loss
    OR employee recovers State compensation for property damage

dependant recovers State compensation
    AND State workers compensation is recovered by dependant of deceased employee
    AND State workers compensation is for benefit of dependant of deceased employee
    AND recovery is in respect of injury that resulted in death

compensation not payable when State compensation recovered
    OR employee recovers State workers compensation
        AND compensation is not payable under this Act to employee
        AND compensation is not payable in respect of that injury loss or damage
    OR dependant recovers State compensation
        AND compensation is not payable under this Act to dependant
        AND compensation is not payable in respect of injury that resulted in death

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 118 Double benefits
Commonwealth compensation paid to employee
    AND compensation has been paid by Commonwealth under this Act
    AND compensation is paid to employee
    AND compensation is in respect of injury or loss of or damage to property

Commonwealth compensation paid to dependant
    AND compensation has been paid by Commonwealth under this Act
    AND compensation is paid to dependant of deceased employee
    AND compensation is for benefit of dependant of deceased employee

employee recovers State compensation after Commonwealth payment
    AND Commonwealth compensation paid to employee
    AND State workers compensation is recovered by employee
    AND recovery is in respect of that injury loss or damage

dependant recovers State compensation after Commonwealth payment
    AND Commonwealth compensation paid to dependant
    AND State workers compensation is recovered by employee
    AND recovery is in respect of injury that resulted in death
    AND recovery is for benefit of dependant

State compensation recovered after Commonwealth payment
    OR employee recovers State compensation after Commonwealth payment
    OR dependant recovers State compensation after Commonwealth payment

MRCC may recover compensation paid
    AND State compensation recovered after Commonwealth payment
    AND MRCC may recover amount of compensation paid by Commonwealth
    AND recovery is from person to whom it was paid
    AND recovery is in court of competent jurisdiction
    AND recovery is as debt due to Commonwealth

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 118 Double benefits
MRCC received claim
    AND MRCC has received claim

MRCC may require statutory declaration
    AND MRCC received claim
    AND MRCC may require claimant to give statutory declaration
    AND statutory declaration states whether State workers compensation has been paid to claimant
    AND statutory declaration states whether State workers compensation has been paid in respect of claimant
    AND statutory declaration is in respect of injury or loss of or damage to property

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 118 Double benefits
claimant refuses statutory declaration
    AND claimant refuses to give statutory declaration under subsection (3)
    AND claimant refuses without reasonable excuse

claimant fails to give statutory declaration
    AND claimant fails to give statutory declaration under subsection (3)
    AND claimant fails without reasonable excuse

claimant fails to provide statutory declaration without excuse
    OR claimant refuses statutory declaration
    OR claimant fails to give statutory declaration

claimant rights suspended
    AND claimant fails to provide statutory declaration without excuse
    AND claimant's rights to compensation under this Act are suspended
    AND claimant's rights to institute proceedings under this Act are suspended
    AND claimant's rights to continue proceedings under this Act are suspended
    AND suspension is until statutory declaration is given

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 118 Double benefits
compensation not payable during suspension
    AND claimant's right to compensation is suspended under subsection (4)
    AND compensation is not payable in respect of period of suspension

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 119 Compensation where State compensation payable
compensation where State compensation payable
    AND State compensation is payable
    AND compensation under this Act may be reduced

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 120 Notice of departure from Australia etc.
notice of departure from Australia etc.
    AND employee intends to depart from Australia
    AND notice is given to MRCC

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 121B Regulations modifying the operation of this Act
regulations modifying the operation of this Act
    AND regulations may modify operation of this Act

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 122 Regulations
regulations
    AND Governor-General may make regulations

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part IX—Miscellaneous
# Original: 122A Legislative rules
legislative rules
    AND rules may be made under section 122A

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part X—Transitional provisions
# Original: Division 1—Preliminary
injuries suffered before commencing day
    AND injury was suffered before commencing day
    AND injury is covered by this Act
    AND compensation is payable under this Act

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 124 - Application to pre-existing injuries
# Original: "This Act applies to an injury suffered before the commencing day if compensation was payable under the 1912, 1930 or 1971 Acts."
Act applies to pre-existing injury IS TRUE
    OR pre-existing injury virtual node
        AND injury was suffered before commencing day
        AND compensation was payable under 1912 Act
    OR pre-existing injury virtual node
        AND injury was suffered before commencing day
        AND compensation was payable under 1930 Act
    OR pre-existing injury virtual node
        AND injury was suffered before commencing day
        AND compensation was payable under 1971 Act

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part X—Transitional provisions
# Original: 125 Payments under previous Acts
payment was made under 1912 Act
    AND payment was made under 1912 Act

payment was made under 1930 Act
    AND payment was made under 1930 Act

payment was made under 1971 Act
    AND payment was made under 1971 Act

payment made under previous Acts virtual node
    OR payment was made under 1912 Act
    OR payment was made under 1930 Act
    OR payment was made under 1971 Act

payments under previous Acts
    AND payment made under previous Acts virtual node
    AND payment is treated as payment under this Act

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part X—Transitional provisions
# Original: 126 Notices, claims etc. under previous Acts
notice was given under 1912 Act
    AND notice was given under 1912 Act

notice was given under 1930 Act
    AND notice was given under 1930 Act

notice was given under 1971 Act
    AND notice was given under 1971 Act

claim was made under 1912 Act
    AND claim was made under 1912 Act

claim was made under 1930 Act
    AND claim was made under 1930 Act

claim was made under 1971 Act
    AND claim was made under 1971 Act

notice given under previous Acts virtual node
    OR notice was given under 1912 Act
    OR notice was given under 1930 Act
    OR notice was given under 1971 Act

claim made under previous Acts virtual node
    OR claim was made under 1912 Act
    OR claim was made under 1930 Act
    OR claim was made under 1971 Act

notice or claim under previous Acts virtual node
    OR notice given under previous Acts virtual node
    OR claim made under previous Acts virtual node

notices claims etc under previous Acts
    AND notice or claim under previous Acts virtual node
    AND notice or claim is treated as notice or claim under this Act

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part X—Transitional provisions
# Original: 127 Settlements and determinations under previous Acts
settlement was made under 1912 Act
    AND settlement was made under 1912 Act

settlement was made under 1930 Act
    AND settlement was made under 1930 Act

settlement was made under 1971 Act
    AND settlement was made under 1971 Act

determination was made under 1912 Act
    AND determination was made under 1912 Act

determination was made under 1930 Act
    AND determination was made under 1930 Act

determination was made under 1971 Act
    AND determination was made under 1971 Act

settlement made under previous Acts virtual node
    OR settlement was made under 1912 Act
    OR settlement was made under 1930 Act
    OR settlement was made under 1971 Act

determination made under previous Acts virtual node
    OR determination was made under 1912 Act
    OR determination was made under 1930 Act
    OR determination was made under 1971 Act

settlement or determination under previous Acts virtual node
    OR settlement made under previous Acts virtual node
    OR determination made under previous Acts virtual node

settlements and determinations under previous Acts
    AND settlement or determination under previous Acts virtual node
    AND settlement or determination is treated as settlement or determination under this Act

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part X—Transitional provisions
# Original: 128 Liability under previous Acts
liability existed under 1912 Act
    AND liability existed under 1912 Act

liability existed under 1930 Act
    AND liability existed under 1930 Act

liability existed under 1971 Act
    AND liability existed under 1971 Act

liability under previous Acts virtual node
    OR liability existed under 1912 Act
    OR liability existed under 1930 Act
    OR liability existed under 1971 Act

liability under previous Acts
    AND liability under previous Acts virtual node
    AND liability is treated as liability under this Act

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part X—Transitional provisions
# Original: 129A Reconsideration and review of certain determinations under 1971 Act
reconsideration and review of certain determinations under 1971 Act
    AND determination was made under 1971 Act
    AND determination may be reconsidered under this Act
    AND determination may be reviewed under this Act

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part X—Transitional provisions
# Original: 130 Money and investments held under 1971 Act
money was held under 1971 Act
    AND money was held under 1971 Act

investments were held under 1971 Act
    AND investments were held under 1971 Act

money or investments held under 1971 Act virtual node
    OR money was held under 1971 Act
    OR investments were held under 1971 Act

money and investments held under 1971 Act
    AND money or investments held under 1971 Act virtual node
    AND money or investments are treated as held under this Act

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part X—Transitional provisions
# Original: 131 Former employees under 65 who are in receipt of superannuation benefits and are unable to engage in any work
section 131 applies to former employee
    AND former employee was under 65 on commencing day
    AND former employee was in receipt of pension under superannuation scheme on commencing day
    AND former employee is not capable of engaging in any work

total benefit was 95% or more of normal weekly earnings
    AND former employee's total benefit immediately before commencing day >= 95% of normal weekly earnings as at commencing day

total benefit was 70% to 95% of normal weekly earnings
    AND former employee's total benefit immediately before commencing day >= 70% of normal weekly earnings as at commencing day
    AND former employee's total benefit immediately before commencing day < 95% of normal weekly earnings as at commencing day

total benefit was less than 70% of normal weekly earnings
    AND former employee's total benefit immediately before commencing day < 70% of normal weekly earnings as at commencing day

compensation under subsection 2 IS CALC ((95% of normal weekly earnings as at commencing day) - superannuation amount)
    NEEDS normal weekly earnings as at commencing day
    NEEDS superannuation amount

compensation under subsection 3
    AND compensation amount = employee's 1971 amount

compensation under subsection 4 IS CALC ((70% of normal weekly earnings for the time being) - superannuation amount)
    NEEDS normal weekly earnings for the time being
    NEEDS superannuation amount

compensation payable under section 131 virtual node
    OR total benefit was 95% or more of normal weekly earnings
        AND compensation amount = compensation under subsection 2
    OR total benefit was 70% to 95% of normal weekly earnings
        AND compensation amount = compensation under subsection 3
    OR total benefit was less than 70% of normal weekly earnings
        AND compensation amount = compensation under subsection 4

compensation is payable under section 131
    AND section 131 applies to former employee
    AND compensation payable under section 131 virtual node

compensation increase due to normal weekly earnings increase
    AND normal weekly earnings have increased
    AND compensation is payable under section 131
    AND compensation amount under section 131 < 70% of increased normal weekly earnings
    AND compensation amount must be increased until equal to 70% of increased normal weekly earnings

superannuation amount increased
    AND superannuation amount of former employee has increased

reduction amount equal to increase
    AND reduction amount = amount of increase in superannuation

reduction amount to maintain 70% combined benefit IS CALC ((70% of normal weekly earnings as at date of increase) - superannuation amount after increase)
    NEEDS normal weekly earnings as at date of increase
    NEEDS superannuation amount after increase

reduction amount is lesser of two amounts
    AND reduction amount = MIN(reduction amount equal to increase, reduction amount to maintain 70% combined benefit)

compensation reduction required
    AND superannuation amount increased
    AND compensation is payable under section 131
    AND compensation amount must be reduced by reduction amount
    AND reduction amount is lesser of two amounts
    AND NOT reduction would result in combined benefit less than 70% of normal weekly earnings

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part X—Transitional provisions
# Original: 132 Former employees under 65 who are not in receipt of superannuation benefits and are unable to engage in any work
section 132 applies to former employee
    AND former employee was under 65 on commencing day
    AND former employee was not in receipt of pension under superannuation scheme on commencing day
    AND former employee is not capable of engaging in any work

1971 amount was 95% or more of normal weekly earnings
    AND former employee's 1971 amount >= 95% of normal weekly earnings as at commencing day

1971 amount was 70% to 95% of normal weekly earnings
    AND former employee's 1971 amount >= 70% of normal weekly earnings as at commencing day
    AND former employee's 1971 amount < 95% of normal weekly earnings as at commencing day

1971 amount was less than 70% of normal weekly earnings
    AND former employee's 1971 amount < 70% of normal weekly earnings as at commencing day

compensation under subsection 2 IS CALC (95% of normal weekly earnings as at commencing day)
    NEEDS normal weekly earnings as at commencing day

compensation under subsection 3
    AND compensation amount = employee's 1971 amount

compensation under subsection 4 IS CALC (70% of normal weekly earnings as at commencing day)
    NEEDS normal weekly earnings as at commencing day

compensation payable under section 132 virtual node
    OR 1971 amount was 95% or more of normal weekly earnings
        AND compensation amount = compensation under subsection 2
    OR 1971 amount was 70% to 95% of normal weekly earnings
        AND compensation amount = compensation under subsection 3
    OR 1971 amount was less than 70% of normal weekly earnings
        AND compensation amount = compensation under subsection 4

compensation increase due to normal weekly earnings increase for section 132
    AND normal weekly earnings have increased
    AND compensation amount under section 132 < 70% of increased normal weekly earnings
    AND compensation amount must be increased until equal to 70% of increased normal weekly earnings

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part X—Transitional provisions
# Original: 132A Former employees under 65 who are capable of engaging in any work
section 132A applies to former employee
    AND former employee was under 65 on commencing day
    AND former employee is capable of engaging in any work

former employee in receipt of superannuation on commencing day
    AND former employee was in receipt of pension under superannuation scheme on commencing day

former employee not in receipt of superannuation on commencing day
    AND former employee was not in receipt of pension under superannuation scheme on commencing day

amount able to earn in suitable employment
    AND amount per week = amount former employee is able to earn in suitable employment

amount earns from any employment
    AND amount per week = amount former employee earns from any employment including self employment

greater of earning amounts IS CALC (MAX(amount able to earn in suitable employment, amount earns from any employment))
    NEEDS amount able to earn in suitable employment
    NEEDS amount earns from any employment

compensation under section 131 less earnings IS CALC (compensation under section 131 - greater of earning amounts)
    NEEDS compensation under section 131
    NEEDS greater of earning amounts

compensation under section 20
    AND compensation amount = amount that would be payable under section 20

greater of compensation amounts for superannuated employee IS CALC (MAX(compensation under section 131 less earnings, compensation under section 20))
    NEEDS compensation under section 131 less earnings
    NEEDS compensation under section 20

compensation under section 132 less earnings IS CALC (compensation under section 132 - greater of earning amounts)
    NEEDS compensation under section 132
    NEEDS greater of earning amounts

compensation under section 19 less 5% IS CALC (compensation under section 19 - (5% of normal weekly earnings))
    NEEDS compensation under section 19
    NEEDS normal weekly earnings

greater of compensation amounts for non-superannuated employee IS CALC (MAX(compensation under section 132 less earnings, compensation under section 19 less 5%))
    NEEDS compensation under section 132 less earnings
    NEEDS compensation under section 19 less 5%

compensation payable under section 132A virtual node
    OR former employee in receipt of superannuation on commencing day
        AND compensation amount = greater of compensation amounts for superannuated employee
    OR former employee not in receipt of superannuation on commencing day
        AND compensation amount = greater of compensation amounts for non-superannuated employee

factors for determining suitable employment
    AND MRCC must have regard to factors mentioned in paragraphs 19(4)(a) to (g)
    AND factors are applied as if they referred to former employee

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: Division 1—Preliminary
simplified outline of this Part
    AND this Part provides for operation of this Act in relation to defence-related injuries and deaths
    AND this Part provides for management of defence-related claims
    AND this Part provides for treatment of certain defence-related injuries
    AND this Part provides for administrative matters

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Section 134 - Reduction on reaching pension age
# Original: "The amount of compensation payable... must be reduced by an amount calculated under the formula: (5 × (pension age − age as at commencing day)) / 100 × amount of weekly compensation."
reduction amount on reaching pension age IS CALC ((pension-age taper numerator * (pension age - age as at commencing day)) / pension-age taper denominator *weekly compensation)
    NEEDS pension age
    NEEDS age as at commencing day
    NEEDS weekly compensation

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 141 Definitions
claim is made by member of Defence Force
    AND claim is made by member of Defence Force

claim is made by dependant of member of Defence Force
    AND claim is made by dependant of member of Defence Force

claimant is eligible virtual node
    OR claim is made by member of Defence Force
    OR claim is made by dependant of member of Defence Force

defence-related claim
    AND claimant is eligible virtual node
    AND claim relates to injury or death
    AND injury or death is defence-related

defence-related injury
    AND injury is suffered by member of Defence Force
    AND injury arises out of or in course of employment
    AND employment is defence service

defence-related death
    AND death is of member of Defence Force
    AND death results from defence-related injury

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 141 Definitions
Defence Force definition
    AND Defence Force has meaning given by MRCA

defence service definition
    AND defence service has meaning given by MRCA

claim timing requirements
    AND claim is made under this Act
    AND claim is made before or after MRCA commencement date
    AND claim includes claim made but not determined before MRCA commencement date

claim relates to injury
    AND injury is suffered by member of Defence Force
    AND injury arises out of or in course of employment
    AND employment is defence service

claim relates to loss
    AND loss is suffered by member of Defence Force
    AND loss arises out of or in course of employment
    AND employment is defence service

claim relates to damage   
    AND damage is suffered by member of Defence Force
    AND damage arises out of or in course of employment
    AND employment is defence service

claim relates to death
    AND death is of member of Defence Force
    AND death results from defence-related injury

claim relates to injury loss damage or death virtual node
    OR claim relates to injury
    OR claim relates to loss
    OR claim relates to damage
    OR claim relates to death

MRCA does not apply to claim
    AND MRCA does not apply to claim

claim relates to defence service before MRCA commencement date
    AND claim relates to defence service
    AND defence service occurred before MRCA commencement date

defence-related claim
    AND claim timing requirements
    AND claim relates to injury loss damage or death virtual node
    AND MRCA does not apply to claim
    AND claim relates to defence service before MRCA commencement date

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 142 Functions of MRCC
functions of MRCC
    AND MRCC manages defence-related claims
    AND MRCC makes determinations in relation to defence-related claims
    AND MRCC provides information in relation to defence-related claims

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 143 Giving copies of defence-related claims etc.
giving copies of defence-related claims
    AND MRCC gives copies of defence-related claims to Defence Department
    AND MRCC gives copies of determinations to Defence Department
    AND MRCC gives copies of other documents to Defence Department

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 144 Provisions relating to management of claims etc.
provisions relating to management of claims
    AND MRCC manages defence-related claims in accordance with this Part
    AND Defence Department cooperates with MRCC in management of claims
    AND Defence Department provides information to MRCC

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 144A Persons entitled to treatment under other legislation not entitled to certain compensation
employee eligible for treatment under Nuclear Tests Act
    AND employee is eligible to be provided with treatment under section 7 of Australian Participants in British Nuclear Tests and British Commonwealth Occupation Force (Treatment) Act 2006

employee entitled to treatment under MRCA section 281
    AND employee is entitled to be provided with treatment under section 281 of MRCA for any injury or disease

employee entitled to treatment under MRCA section 282
    AND employee is entitled to be provided with treatment under section 282 of MRCA for any injury or disease

employee entitled to treatment under MRCA virtual node
    OR employee entitled to treatment under MRCA section 281
    OR employee entitled to treatment under MRCA section 282

employee eligible for treatment under Special Access Act
    AND employee is eligible to be provided with treatment under section 7 of Treatment Benefits (Special Access) Act 2019
    AND eligibility is as result of claim to establish eligibility having been determined under that Act

employee eligible for treatment under VEA section 53D
    AND employee is eligible for treatment under section 53D of Veterans Entitlements Act 1986 for any injury or disease

employee eligible for treatment under VEA subsection 85(3)
    AND employee is eligible for treatment under subsection 85(3) of Veterans Entitlements Act 1986 for any injury or disease

employee eligible for treatment under VEA subsection 85(4)
    AND employee is eligible for treatment under subsection 85(4) of Veterans Entitlements Act 1986 for any injury or disease

employee eligible for treatment under VEA subsection 85(4A)
    AND employee is eligible for treatment under subsection 85(4A) of Veterans Entitlements Act 1986 for any injury or disease

employee eligible for treatment under VEA subsection 85(4B)
    AND employee is eligible for treatment under subsection 85(4B) of Veterans Entitlements Act 1986 for any injury or disease

employee eligible for treatment under VEA subsection 85(5)
    AND employee is eligible for treatment under subsection 85(5) of Veterans Entitlements Act 1986 for any injury or disease

employee eligible for treatment under VEA subsection 85(7)
    AND employee is eligible for treatment under subsection 85(7) of Veterans Entitlements Act 1986 for any injury or disease

employee eligible for treatment under VEA subsection 85(7A)
    AND employee is eligible for treatment under subsection 85(7A) of Veterans Entitlements Act 1986 for any injury or disease

employee eligible for treatment under Veterans Entitlements Act virtual node
    OR employee eligible for treatment under VEA section 53D
    OR employee eligible for treatment under VEA subsection 85(3)
    OR employee eligible for treatment under VEA subsection 85(4)
    OR employee eligible for treatment under VEA subsection 85(4A)
    OR employee eligible for treatment under VEA subsection 85(4B)
    OR employee eligible for treatment under VEA subsection 85(5)
    OR employee eligible for treatment under VEA subsection 85(7)
    OR employee eligible for treatment under VEA subsection 85(7A)

employee eligible for treatment under other legislation virtual node
    OR employee eligible for treatment under Nuclear Tests Act
    OR employee entitled to treatment under MRCA virtual node
    OR employee eligible for treatment under Special Access Act
    OR employee eligible for treatment under Veterans Entitlements Act virtual node

MRCC not liable to pay compensation for medical treatment
    AND MRCC is not liable under subsection 16(1) of this Act
    AND compensation is in respect of cost of medical treatment obtained in relation to injury of employee
    AND employee eligible for treatment under other legislation virtual node
    AND NOT exceptional circumstances determination applies

exceptional circumstances exist
    AND MRCC is satisfied that there are exceptional circumstances

exceptional circumstances determination made
    AND exceptional circumstances exist
    AND MRCC determines in writing that subsection (1) does not apply
    AND determination is in relation to an employee and an injury
    AND determination specifies a day from which subsection (1) does not apply
    AND MRCC notifies employee of determination within 7 days of determination being made
    AND determination is not a legislative instrument

exceptional circumstances determination applies
    AND exceptional circumstances determination made
    AND specified day has arrived

MRCC liable to pay compensation despite other legislation
    AND MRCC is not liable under subsection 16(1) of this Act
    AND compensation is in respect of cost of medical treatment obtained in relation to injury of employee
    AND employee eligible for treatment under other legislation virtual node
    AND exceptional circumstances determination applies

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 144B Treatment of certain defence-related injuries to be provided under the MRCA or the Veterans' Entitlements Act 1986
treatment provider virtual node
    OR treatment is provided under MRCA
    OR treatment is provided under Veterans Entitlements Act 1986

treatment of certain defence-related injuries
    AND injury is defence-related injury
    AND treatment provider virtual node

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 144C Exceptional circumstances determination
exceptional circumstances exist
    AND MRCC is satisfied that there are exceptional circumstances

determination purpose virtual node
    OR determination relates to treatment of defence-related injury
    OR determination relates to compensation for defence-related injury

exceptional circumstances determination made
    AND exceptional circumstances exist
    AND MRCC makes determination in exceptional circumstances
    AND determination purpose virtual node

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 145 Relevant authority
relevant authority
    AND relevant authority is MRCC
    AND relevant authority is responsible for defence-related claims

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 146 Rehabilitation authority etc.
rehabilitation authority
    AND rehabilitation authority is responsible for rehabilitation of members of Defence Force
    AND rehabilitation authority is responsible for rehabilitation of dependants of members of Defence Force

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 147 Notice to the Chief of the Defence Force
notice to Chief of the Defence Force
    AND MRCC gives notice to Chief of the Defence Force
    AND notice relates to defence-related claims
    AND notice relates to determinations

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 148 Rehabilitation programs
rehabilitation programs
    AND rehabilitation authority provides rehabilitation programs
    AND rehabilitation programs are for members of Defence Force
    AND rehabilitation programs are for dependants of members of Defence Force

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 149 Directions by Minister
directions by Minister
    AND Minister may give directions to MRCC
    AND directions relate to defence-related claims
    AND directions relate to management of claims

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 151 – MRCC may obtain information etc.
MRCC may give written notice to provide information
    AND MRCC may give written notice to any person
    AND notice requires person to provide information to MRCC or specified staff member
    AND information is for purposes of this Act

MRCC may give written notice to produce documents
    AND MRCC may give written notice to any person
    AND notice requires person to produce documents to MRCC or specified staff member
    AND documents are in custody or under control of person

MRCC may give written notice to appear before staff member
    AND MRCC may give written notice to any person
    AND notice requires person to appear before specified staff member
    AND appearance is to answer questions

MRCC notice requirements virtual node
    OR MRCC may give written notice to provide information
    OR MRCC may give written notice to produce documents
    OR MRCC may give written notice to appear before staff member

person given notice may be employed in Department
    AND person given notice may be employed in or in connection with Department of Commonwealth

person given notice may be employed in State Department
    AND person given notice may be employed in or in connection with Department of State

person given notice may be employed in Territory Department
    AND person given notice may be employed in or in connection with Department of Territory

person given notice may be employed in Department virtual node
    OR person given notice may be employed in Department
    OR person given notice may be employed in State Department
    OR person given notice may be employed in Territory Department

person given notice may be employed by Commonwealth authority
    AND person given notice may be employed by authority of Commonwealth

person given notice may be employed by State authority
    AND person given notice may be employed by authority of State

person given notice may be employed by Territory authority
    AND person given notice may be employed by authority of Territory

person given notice may be employed by authority virtual node
    OR person given notice may be employed by Commonwealth authority
    OR person given notice may be employed by State authority
    OR person given notice may be employed by Territory authority

person given notice may be employed virtual node
    OR person given notice may be employed in Department
    OR person given notice may be employed by authority

eligible persons for notice virtual node
    OR person given notice may be Secretary of Defence Department
    OR person given notice may be Secretary of Department
    OR person given notice may be Chief of Defence Force
    OR person given notice may be employed virtual node

notice must specify period and manner for information or documents
    AND notice must specify period within which person must comply
    AND notice must specify manner in which person must comply

notice must specify time and place for appearance
    AND notice must specify time at which person must appear before staff member
    AND notice must specify place at which person must appear before staff member

notice specification requirements virtual node
    OR notice must specify period and manner for information or documents
    OR notice must specify time and place for appearance

notice given date
    AND notice is given on specific date

compliance deadline date
    AND compliance deadline is at least 14 days after notice given date

compliance period is at least 14 days
    AND notice specification requirements virtual node
    AND notice given date
    AND compliance deadline date

MRCC may require verification by oath or affirmation
    AND MRCC may require information or answers to be verified by oath or affirmation
    AND verification may be either orally or in writing

staff member may administer oath or affirmation
    AND staff member to whom information or answers are verified may administer oath or affirmation

section does not require contravention of Commonwealth law
    AND section does not require person to give information
    AND section does not require person to produce document
    AND section does not require person to give evidence
    AND to extent that doing so would contravene law of Commonwealth not being law of Territory

section binds Crown but not liable for prosecution
    AND section binds Crown in each of its capacities
    AND section does not make Crown liable to be prosecuted for offence

person commits offence if fails to comply with notice
    AND person fails to comply with notice under section 151
    AND person commits offence

offence is of strict liability
    AND offence against subsection (9) is offence of strict liability

subsection (9) does not apply if person incapable of compliance
    AND subsection (9) does not apply to extent that person is not capable of complying with notice

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 151AA – Self incrimination
individual not excused from giving information
    AND individual is not excused from giving information under section 151
    AND individual is not excused from giving evidence under section 151
    AND individual is not excused from producing document under section 151

ground is self incrimination
    AND ground is that information or evidence might tend to incriminate individual

ground is exposure to penalty
    AND ground is that information or evidence might expose individual to penalty

grounds for not being excused virtual node
    OR ground is self incrimination
    OR ground is exposure to penalty

individual not excused from giving information on self incrimination ground
    AND individual not excused from giving information
    AND grounds for not being excused virtual node

information or evidence not admissible in evidence
    AND information or evidence given under section 151 is not admissible in evidence against individual
    AND document produced under section 151 is not admissible in evidence against individual
    AND giving information or evidence is not admissible in evidence against individual
    AND producing document is not admissible in evidence against individual
    AND any information obtained as consequence is not admissible in evidence against individual
    AND any document obtained as consequence is not admissible in evidence against individual
    AND any thing obtained as consequence is not admissible in evidence against individual
    AND exception is proceedings for offence against section 137.1 or 137.2 of Criminal Code relating to this Act

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 151A – Giving information
State or Territory law cannot prevent giving information
    AND nothing in law of State or Territory operates to prevent person from giving information
    AND nothing in law of State or Territory operates to prevent person from producing documents
    AND nothing in law of State or Territory operates to prevent person from giving evidence
    AND purpose is for purposes of this Act

MRCC may provide information to Secretary of National Health Act Department
    AND MRCC may provide information to Secretary of Department administered by Minister who administers National Health Act 1953
    AND purpose is purposes of that Department

MRCC may provide information to Secretary of Aged Care Act Department
    AND MRCC may provide information to Secretary of Department administered by Minister who administers Aged Care Act 1997
    AND purpose is purposes of that Department

MRCC may provide information to CEO of Services Australia
    AND MRCC may provide information to Chief Executive Officer of Services Australia
    AND purpose is purposes of Services Australia

MRCC may provide information to Chief Executive Centrelink
    AND MRCC may provide information to Chief Executive Centrelink
    AND purpose is purposes of Centrelink

MRCC may provide information to Chief Executive Medicare
    AND MRCC may provide information to Chief Executive Medicare
    AND purpose is purposes of Medicare

function or power is under Act administered by CSC
    AND function or power is under Act administered by CSC

function or power is under instrument under Act administered by CSC
    AND function or power is under instrument under Act administered by CSC

function or power basis virtual node
    OR function or power is under Act administered by CSC
    OR function or power is under instrument under Act administered by CSC

MRCC may provide information to Commonwealth Superannuation Corporation
    AND MRCC may provide information to Commonwealth Superannuation Corporation
    AND purpose is relating to performance of function or exercise of power by Corporation
    AND function or power basis virtual node

MRCC may provide information to receiving Commonwealth body
    AND MRCC may provide information to receiving Commonwealth body
    AND purpose is relating to performance of function or exercise of power by that body

information provision under table virtual node
    OR MRCC may provide information to Secretary of National Health Act Department
    OR MRCC may provide information to Secretary of Aged Care Act Department
    OR MRCC may provide information to CEO of Services Australia
    OR MRCC may provide information to Chief Executive Centrelink
    OR MRCC may provide information to Chief Executive Medicare
    OR MRCC may provide information to Commonwealth Superannuation Corporation
    OR MRCC may provide information to receiving Commonwealth body

MRCC may provide information to Secretary of Defence Department for litigation
    AND MRCC may provide information to Secretary of Defence Department
    AND purpose relates to litigation involving injury disease or death of employee
    AND claim has been made under this Act

MRCC may provide information to Secretary of Defence Department for monitoring OHS
    AND MRCC may provide information to Secretary of Defence Department
    AND purpose relates to monitoring performance of Defence Force in relation to occupational health and safety

MRCC may provide information to Secretary of Defence Department for cost monitoring
    AND MRCC may provide information to Secretary of Defence Department
    AND purpose relates to monitoring cost to Commonwealth of injuries diseases or deaths of employees
    AND claims have been made under this Act

information provision to Defence Department virtual node
    OR MRCC may provide information to Secretary of Defence Department for litigation
    OR MRCC may provide information to Secretary of Defence Department for monitoring OHS
    OR MRCC may provide information to Secretary of Defence Department for cost monitoring

purpose relates to reconsideration under MRCA
    AND purpose relates to reconsideration under section 347 of MRCA

purpose relates to review under MRCA
    AND purpose relates to review under Part 4 of Chapter 8 of MRCA

purpose for reconsideration or review virtual node
    OR purpose relates to reconsideration under MRCA
    OR purpose relates to review under MRCA

MRCC may provide information to Chief of Defence Force for reconsideration
    AND MRCC may provide information to Chief of Defence Force
    AND purpose for reconsideration or review virtual node
    AND reconsideration or review is of determination made under this Act
    AND determination is about acceptance of liability for injury disease or death

employee entitled to compensation for medical treatment
    AND person who is or was employee is entitled to compensation for medical treatment under this Act

treatment provided through arrangement with non-Commonwealth entity
    AND treatment is provided to person through arrangement
    AND arrangement includes contractual arrangement
    AND arrangement is with body that is not corporate Commonwealth entity
    AND arrangement is with body that is not non corporate Commonwealth entity

MRCC may provide treatment information to receiving Commonwealth body
    AND MRCC may provide information that relates to provision of treatment
    AND information is provided to receiving Commonwealth body
    AND purpose relates to performance of function or exercise of power by that body

treatment information provision virtual node
    AND employee entitled to compensation for medical treatment
    AND treatment provided through arrangement with non-Commonwealth entity
    AND MRCC may provide treatment information to receiving Commonwealth body

information obtained under subsection 1
    AND information is obtained under information provision under table virtual node

information obtained under subsection 1A
    AND information is obtained under information provision to Defence Department virtual node

information obtained under subsection 1B
    AND information is obtained under MRCC may provide information to Chief of Defence Force for reconsideration

information obtained under subsection 1C
    AND information is obtained under treatment information provision virtual node

information obtained under any subsection virtual node
    OR information obtained under subsection 1
    OR information obtained under subsection 1A
    OR information obtained under subsection 1B
    OR information obtained under subsection 1C

person must not use information for other purposes
    AND person must not use information obtained under any subsection virtual node
    AND use is for purpose other than those purposes

person must not further disclose information for other purposes
    AND person must not further disclose information obtained under any subsection virtual node
    AND disclosure is for purpose other than those purposes

information used or disclosed is authorised by law
    AND information is used or disclosed in accordance with this section
    AND information is taken for purposes of Privacy Act 1988 to be authorised by law

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 152 Delegation
delegation
    AND MRCC may delegate functions to other persons
    AND delegation is in writing
    AND delegation is subject to conditions

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 154 Settlements and determinations etc. under the 1912 Act, the 1930 Act or the 1971 Act
settlement was made under 1912 Act
    AND settlement was made under 1912 Act

settlement was made under 1930 Act
    AND settlement was made under 1930 Act

settlement was made under 1971 Act
    AND settlement was made under 1971 Act

determination was made under 1912 Act
    AND determination was made under 1912 Act

determination was made under 1930 Act
    AND determination was made under 1930 Act

determination was made under 1971 Act
    AND determination was made under 1971 Act

settlement made under previous Acts virtual node
    OR settlement was made under 1912 Act
    OR settlement was made under 1930 Act
    OR settlement was made under 1971 Act

determination made under previous Acts virtual node
    OR determination was made under 1912 Act
    OR determination was made under 1930 Act
    OR determination was made under 1971 Act

settlement or determination under previous Acts virtual node
    OR settlement made under previous Acts virtual node
    OR determination made under previous Acts virtual node

settlements and determinations under previous Acts
    AND settlement or determination under previous Acts virtual node
    AND settlement or determination is treated as settlement or determination under this Act

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 157 Application of certain provisions to Defence Department
application of provisions to Defence Department
    AND certain provisions of this Act apply to Defence Department
    AND provisions relate to management of defence-related claims
    AND provisions relate to treatment of defence-related injuries

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 160 Appropriation
appropriation
    AND money is appropriated for purposes of this Part
    AND money is paid out of Consolidated Revenue Fund

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Part XI—Operation of this Act in relation to certain defence-related injuries and deaths etc.
# Original: 161 Annual report
annual report
    AND MRCC prepares annual report
    AND annual report relates to operation of this Part
    AND annual report is presented to Parliament

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Endnotes
# Original: Endnote 1 About the endnotes
about the endnotes
    AND endnotes provide information about this compilation
    AND endnotes include information about amending laws
    AND endnotes include amendment history of provisions

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Endnotes
# Original: Endnote 2 Abbreviation key
abbreviation key
    AND abbreviations are used in this compilation
    AND abbreviations are explained in this endnote
    AND abbreviations include Act names and other terms

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Endnotes
# Original: Endnote 3 Legislation history
legislation history
    AND legislation history shows when provisions were amended
    AND legislation history shows which Acts amended provisions
    AND legislation history shows when amendments commenced

# Reference: https://www.legislation.gov.au/Details/C2025C00325
# Section: Endnotes
# Original: Endnote 4 Amendment history
amendment history
    AND amendment history shows details of amendments
    AND amendment history shows which provisions were amended
    AND amendment history shows effect of amendments