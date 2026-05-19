FIXED Act name IS "Defence Force (Home Loans Assistance) Act 1990"
FIXED commencing day IS 15/05/1991
FIXED DSH Act IS "Defence Service Homes Act 1918"
FIXED first service date threshold IS 14/05/1985
FIXED statutory training factor IS 0.625
FIXED basic service period years IS 5
FIXED finishing day for member certificate issue IS 30/06/2008
FIXED finishing day general IS 30/06/2010
FIXED former member eligibility period years IS 2
FIXED rejoining member window years IS 2
FIXED incapacitated person rejoining window years IS 2
FIXED minimum effective full-time service after basic service period months IS 6
FIXED certificate validity period months IS 12
FIXED loan discharge application window months IS 12
FIXED surviving spouse application window years IS 2
FIXED maximum advanced amount IS 80000
FIXED maximum advanced amount for joint loan IS 160000
FIXED minimum loan amount IS 10000
FIXED minimum loan increase amount IS 10000
FIXED entitlement period maximum years standard IS 20
FIXED entitlement period maximum years operational service member 3A1 IS 16
FIXED entitlement period maximum years warlike service member IS 25
FIXED entitlement period maximum years incapacitated person IS 10
FIXED loan repayment term in months IS 300
FIXED subsidy interest component multiplier IS 0.4
FIXED Middle East operational duty period start date IS 02/08/1990
FIXED Middle East operational duty period end date IS 09/06/1991
FIXED Middle-East operational area AS LIST
    ITEM Kuwait
    ITEM Iraq
    ITEM Bahrain
    ITEM Oman
    ITEM Qatar
    ITEM Saudi Arabia
    ITEM United Arab Emirates
    ITEM Island of Cyprus
    ITEM Gulf of Suez
    ITEM Gulf of Aqaba
    ITEM Red Sea
    ITEM Gulf of Aden
    ITEM Persian Gulf
    ITEM Gulf of Oman
    ITEM Arabian Sea north of boundary
    ITEM Suez Canal
    ITEM Mediterranean Sea east of 30E
FIXED valid loan purposes AS LIST
    ITEM buy land and build the house
    ITEM build house on land already owned
    ITEM buy house together with land
    ITEM complete partly built house already owned
    ITEM enlarge renovate or repair complete house already owned
    ITEM discharge another loan for a valid purpose
FIXED valid loan increase purposes AS LIST
    ITEM enlarge renovate or repair the house
    ITEM construct permanent improvements on the land
    ITEM discharge another loan used for a valid purpose

INPUT person is a member of the Defence Force AS BOOLEAN
INPUT person is a member of the Reserves AS BOOLEAN
INPUT first service in Defence Force began date AS DATE
INPUT person's resignation retirement or discharge date AS DATE
INPUT person was discharged from the Defence Force because of a compensable disability AS BOOLEAN
INPUT compensation was or is payable for disability AS BOOLEAN
INPUT person has made an election under section 4BA of the DSH Act that has not been revoked AS BOOLEAN
INPUT is covered by paragraph ga of the definition of Australian Soldier in subsection 4(1) of the DSH Act AS BOOLEAN
INPUT is an Australian Soldier for the purposes of the DSH Act under specified paragraphs AS BOOLEAN
INPUT person has effective full-time service years AS NUMBER
INPUT person has statutory training obligation years AS NUMBER
INPUT person has completed a period of effective full-time service and statutory training obligation without a break AS BOOLEAN
INPUT person again becomes a member AS BOOLEAN
INPUT date person again becomes a member AS DATE
INPUT service history AS LIST
    ITEM service type AS TEXT
    ITEM start date AS DATE
    ITEM end date AS DATE
    ITEM is allotted for duty in Middle-East operational area AS BOOLEAN
    ITEM duty includes period between 02/08/1990 and 09/06/1991 AS BOOLEAN
    ITEM allotment instrument signed by Vice Chief of the Defence Force AS BOOLEAN
    ITEM is declared warlike service AS BOOLEAN
    ITEM repatriated from warlike service due to wounds injury or illness AS BOOLEAN
    ITEM expected posting period on warlike service months AS NUMBER
    ITEM actual warlike service months AS NUMBER
INPUT person is a surviving spouse or de facto partner AS BOOLEAN
INPUT person was living with deceased person immediately before death AS BOOLEAN
INPUT deceased person's date of death AS DATE
INPUT application for entitlement certificate date AS DATE
INPUT number of entitlement certificates previously issued AS NUMBER
INPUT at least one previous certificate was issued after discharge AS BOOLEAN
INPUT compensable disability caused or contributed to failure to apply within 2 year period AS BOOLEAN
INPUT has previously received a subsidised loan AS BOOLEAN
INPUT previous loan discharged due to destruction of house AS BOOLEAN
INPUT previous loan discharged due to compulsory acquisition AS BOOLEAN
INPUT previous loan discharged due to court order sale AS BOOLEAN
INPUT previous loan discharge date AS DATE
INPUT previous loan sale was reasonably necessary as a result of disability AS BOOLEAN
INPUT current date AS DATE
INPUT advanced amount AS NUMBER
INPUT wishes to increase advanced amount AS BOOLEAN
INPUT proposed loan increase amount AS NUMBER
INPUT spouse or de facto partner owns a house in Australia other than the loan house AS BOOLEAN
INPUT subsidy under Defence Home Ownership Assistance Scheme Act 2008 is or has been payable AS BOOLEAN
INPUT used subsidy period months AS NUMBER
INPUT house is owned solely by person or jointly with spouse or de facto partner AS BOOLEAN
INPUT house is used as a home for the person and family AS BOOLEAN
INPUT house is suitable for use as a home AS BOOLEAN
INPUT house is not ordinarily used for carrying on a business trade or profession AS BOOLEAN
INPUT loan is secured by a first mortgage AS BOOLEAN
INPUT loan has been used for a valid purpose AS BOOLEAN
INPUT loan has been used for a valid loan increase purpose AS BOOLEAN
INPUT benchmark rate AS NUMBER
INPUT person's status for entitlement period AS TEXT
INPUT years of subsidy service after basic period AS NUMBER
INPUT subsidy service years AS NUMBER
INPUT additional years for warlike service AS NUMBER
INPUT warlike service period months AS NUMBER
INPUT total borrowed amount AS NUMBER
INPUT maximum allowed amount AS NUMBER
INPUT is joint loan to entitled spouses AS BOOLEAN
INPUT amount on which subsidy is payable AS NUMBER
INPUT RMR amount AS NUMBER
INPUT monthly subsidy amount AS NUMBER
INPUT DSH Act does not apply AS BOOLEAN
INPUT has completed the basic service period AS BOOLEAN
INPUT has completed the training period AS BOOLEAN
INPUT is not the holder of an entitlement certificate that is in force AS BOOLEAN
INPUT subsidy period has not ended AS BOOLEAN
INPUT has not already been issued with an entitlement certificate on or after 1 July 2008 AS BOOLEAN
INPUT special circumstances for re-issue apply AS BOOLEAN
INPUT each borrower has consented to recovery of amounts AS BOOLEAN
INPUT person or spouse is not the owner of any other house in Australia AS BOOLEAN
INPUT house ownership and use criteria are met AS BOOLEAN
INPUT not excluded by section 20A AS BOOLEAN
INPUT not excluded by section 20(4) AS BOOLEAN
INPUT entitlement period years AS NUMBER
INPUT entitlement period calculation AS NUMBER
INPUT all outstanding amounts due under the loan are paid AS BOOLEAN
INPUT subsidy period ends AS BOOLEAN
INPUT joint tenancy is converted into a tenancy in common AS BOOLEAN
INPUT property is transferred under court order AS BOOLEAN
INPUT property is sold or transferred without approval AS BOOLEAN
INPUT person to whom 30(6) applies dies AS BOOLEAN
INPUT eligible person dies without surviving spouse or de facto partner AS BOOLEAN
INPUT eligible person dies and property transferred to someone other than surviving spouse or de facto partner AS BOOLEAN

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: composite service, in relation to a person who has completed a period of effective full-time service and a period of statutory training obligation without a break between the periods, means a period of service that is worked out as follows: (Statutory training obligation years × statutory training factor) + Effective full-time service years
composite service years IS CALC ( ( person has statutory training obligation years * statutory training factor ) + person has effective full-time service years )
    NEEDS person has statutory training obligation years
    NEEDS statutory training factor
    NEEDS person has effective full-time service years
    NEEDS person has completed a period of effective full-time service and statutory training obligation without a break

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: non-DSH member means: (a) a member whose first service in the Defence Force began after 14 May 1985 and who is not covered by paragraph (ga) of the definition of Australian Soldier in subsection 4(1) of the DSH Act; or (b) a member...who has made an election under section 4BA of the DSH Act that has not been revoked.
non-DSH member
    OR non-DSH member under paragraph a
    OR non-DSH member under paragraph b

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: (a) a member whose first service in the Defence Force began after 14 May 1985 and who is not covered by paragraph (ga) of the definition of Australian Soldier in subsection 4(1) of the DSH Act
non-DSH member under paragraph a
    AND person is a member of the Defence Force
    AND first service in Defence Force began date > first service date threshold
    AND NOT is covered by paragraph ga of the definition of Australian Soldier in subsection 4(1) of the DSH Act

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: (b) a member: (i) whose first service in the Defence Force began on or before 14 May 1985; or (ii) whose first service in the Defence Force began after 14 May 1985 and who is covered by paragraph (ga) of the definition of Australian Soldier in subsection 4(1) of the DSH Act; and who has made an election under section 4BA of the DSH Act that has not been revoked.
non-DSH member under paragraph b
    AND person is a member of the Defence Force
    AND person has made an election under section 4BA of the DSH Act that has not been revoked
    AND first service condition for non-DSH member paragraph b met

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: (b) a member: (i) whose first service in the Defence Force began on or before 14 May 1985; or (ii) whose first service in the Defence Force began after 14 May 1985 and who is covered by paragraph (ga) of the definition of Australian Soldier in subsection 4(1) of the DSH Act
first service condition for non-DSH member paragraph b met
    OR first service in Defence Force began date <= first service date threshold
    OR first service in Defence Force began date > first service date threshold
        AND is covered by paragraph ga of the definition of Australian Soldier in subsection 4(1) of the DSH Act

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3A - Operational service member
# Original: (1) A person is an operational service member for the purposes of this Act if...the person is allotted for duty anywhere within the Middle-East operational area; and the duty includes duty sometime during the period that starts on 2 August 1990 and ends on 9 June 1991.
operational service member under subsection 3A(1)
    AND person is a member of the Defence Force
    AND non-DSH member
    AND NOT ALL service ITERATE: LIST OF service history
        OR operational service virtual one
            AND is allotted for duty in Middle-East operational area
            AND duty includes period between 02/08/1990 and 09/06/1991
            AND allotment instrument signed by Vice Chief of the Defence Force

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3A - Operational service member
# Original: (3) A person is also an operational service member for the purposes of this Act if...the person is a non-DSH member because of an election under section 4BA of the DSH Act; and the person is an Australian Soldier for the purposes of the DSH Act because of paragraph (a), (b), (c), (g) or (ga)...
operational service member under subsection 3A(3)
    AND person is a member of the Defence Force
    AND non-DSH member because of an election
    AND is an Australian Soldier for the purposes of the DSH Act under specified paragraphs

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3A - Operational service member
# Original: the person is a non-DSH member because of an election under section 4BA of the DSH Act
non-DSH member because of an election
    AND person is a member of the Defence Force
    AND person has made an election under section 4BA of the DSH Act that has not been revoked

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3A - Operational service member
# Original: A person is an operational service member for the purposes of this Act if...
is an operational service member
    OR operational service member under subsection 3A(1)
    OR operational service member under subsection 3A(3)

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3B - Warlike service member
# Original: (1) A warlike service member is a member who: (a) is a non-DSH member; and (b) has been allotted for duty declared under subsection 3C(1) to be warlike service; and (c) has performed some or all of that duty.
is a warlike service member
    AND person is a member of the Defence Force
    AND non-DSH member
    AND NOT ALL service ITERATE: LIST OF service history
        OR warlike service virtual one
            AND is declared warlike service
            AND allotment instrument signed by Vice Chief of the Defence Force

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: incapacitated person means: (a) a person who, on or after the commencing day, is discharged from the Defence Force because of a compensable disability; or (b) a person...who, before the commencing day, was discharged from the Defence Force because of a compensable disability...
is an incapacitated person
    OR incapacitated person under paragraph a
    OR incapacitated person under paragraph b

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: (a) a person who, on or after the commencing day, is discharged from the Defence Force because of a compensable disability;
incapacitated person under paragraph a
    AND person's resignation retirement or discharge date >= commencing day
    AND person was discharged from the Defence Force because of a compensable disability

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: (b) a person: (i) whose first service in the Defence Force began after 14 May 1985; and (ii) who is not covered by paragraph (ga) of the definition of Australian Soldier in subsection 4(1) of the DSH Act; and (iii) who, before the commencing day, was discharged from the Defence Force because of a compensable disability; and who, immediately before the discharge: (c) had been a non-DSH member engaged or appointed for a period that would have allowed the person to complete at least 5 years of effective full-time service or composite service; and (d) had completed less than 16 years of effective full-time service or composite service.
incapacitated person under paragraph b
    AND first service in Defence Force began date > first service date threshold
    AND NOT is covered by paragraph ga of the definition of Australian Soldier in subsection 4(1) of the DSH Act
    AND person's resignation retirement or discharge date < commencing day
    AND person was discharged from the Defence Force because of a compensable disability
    AND had been a non-DSH member engaged for at least 5 years service potential
    AND completed years of service < 16

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: rejoining member means a person who...immediately before the resignation, retirement or discharge was an eligible person; and again becomes a member within 2 years after the day on which the resignation, retirement or discharge took effect.
is a rejoining member
    AND was an eligible person immediately before discharge
    AND person again becomes a member
    AND date person again becomes a member - person's resignation retirement or discharge date <= rejoining member window years

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: eligible person means: (a) a person who: (i) is a non-DSH member (other than an operational service member, a warlike service member, a rejoining member or a person covered by paragraph (b) or (d)); and (ii) completes ... the basic service period applicable to the person; or (b) a person who: (i) on or after the commencing day, is discharged from the Defence Force because of a compensable disability... (iv) then completes the basic service period applicable to the person; or (c) an incapacitated person; or (d) a person who: (i) having been an incapacitated person, again becomes a member within 2 years after the day on which his or her discharge as an incapacitated person took effect; and (ii) then completes the basic service period applicable to the person; or (e) a rejoining member; or (f) an operational service member; or (fa) a warlike service member; or (g) a person (other than an incapacitated person) who: (i) ... resigns, retires or is discharged ... (ii) immediately before the resignation, retirement or discharge was an operational service member, a warlike service member or a non-DSH member covered by paragraph (a), (b), (d), (e) or (f); and (iii) has not again become a member; or (h) a person: (i) who is a member of the Reserves; and (ii) who completes the training period applicable to the person; and (iii) to whom the DSH Act does not apply.
eligible person
    OR eligible person under paragraph a
    OR eligible person under paragraph b
    OR eligible person under paragraph c
    OR eligible person under paragraph d
    OR eligible person under paragraph e
    OR eligible person under paragraph f
    OR eligible person under paragraph fa
    OR eligible person under paragraph g
    OR eligible person under paragraph h

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: (a) a person who: (i) is a non-DSH member (other than an operational service member, a warlike service member, a rejoining member or a person covered by paragraph (b) or (d)); and (ii) completes (whether before, on or after the commencing day) the basic service period applicable to the person;
eligible person under paragraph a
    AND non-DSH member
    AND NOT is an operational service member
    AND NOT is a warlike service member
    AND NOT is a rejoining member
    AND NOT eligible person under paragraph b
    AND NOT eligible person under paragraph d
    AND has completed the basic service period

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: (b) a person who: (i) on or after the commencing day, is discharged from the Defence Force because of a compensable disability; and (ii) immediately before the discharge, was a non-DSH member engaged or appointed for a period of less than 5 years; and (iii) again becomes a member within 2 years after the day on which the discharge took effect; and (iv) then completes the basic service period applicable to the person;
eligible person under paragraph b
    AND person's resignation retirement or discharge date >= commencing day
    AND person was discharged from the Defence Force because of a compensable disability
    AND was a non-DSH member engaged for less than 5 years
    AND person again becomes a member
    AND date person again becomes a member - person's resignation retirement or discharge date <= 2
    AND has completed the basic service period

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: (c) an incapacitated person;
eligible person under paragraph c
    AND is an incapacitated person

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: (d) a person who: (i) having been an incapacitated person, again becomes a member within 2 years after the day on which his or her discharge as an incapacitated person took effect; and (ii) then completes the basic service period applicable to the person;
eligible person under paragraph d
    AND was an incapacitated person
    AND person again becomes a member
    AND date person again becomes a member - person's resignation retirement or discharge date <= incapacitated person rejoining window years
    AND has completed the basic service period

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: (e) a rejoining member;
eligible person under paragraph e
    AND is a rejoining member

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: (f) an operational service member;
eligible person under paragraph f
    AND is an operational service member

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: (fa) a warlike service member;
eligible person under paragraph fa
    AND is a warlike service member

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: (g) a person (other than an incapacitated person) who: (i) before, on or after the commencing day resigns, retires or is discharged from the Defence Force; and (ii) immediately before the resignation, retirement or discharge was an operational service member, a warlike service member or a non-DSH member covered by paragraph (a), (b), (d), (e) or (f); and (iii) has not again become a member;
eligible person under paragraph g
    AND NOT is an incapacitated person
    AND NOT person is a member of the Defence Force
    AND was a specified eligible person immediately before discharge
    AND NOT person again becomes a member

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: (ii) immediately before the resignation, retirement or discharge was an operational service member, a warlike service member or a non-DSH member covered by paragraph (a), (b), (d), (e) or (f);
was a specified eligible person immediately before discharge
    OR is an operational service member
    OR is a warlike service member
    OR was a non-DSH member covered by other paragraphs

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 3 - Definitions
# Original: (h) a person: (i) who is a member of the Reserves; and (ii) who completes the training period applicable to the person; and (iii) to whom the DSH Act does not apply.
eligible person under paragraph h
    AND person is a member of the Reserves
    AND has completed the training period
    AND DSH Act does not apply

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 4 - When do former members stop being eligible members?
# Original: (1) An eligible person who is not a member stops being an eligible person...at the end of 2 years after the day on which his or her resignation, retirement or discharge from the Defence Force took effect;
former member is still an eligible person
    OR operational service member under subsection 3A(1)
    OR current date - person's resignation retirement or discharge date <= former member eligibility period years
    OR eligibility period is extended under 4(1A)

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 4 - When do former members stop being eligible members?
# Original: (1A) However, the Secretary may determine in writing that a person covered by paragraph (1)(a) continues to be an eligible person for a specified period beyond the period of 2 years...if...the person is an incapacitated person; and...the compensable disability...caused, or contributed to, the person’s failure to apply...within that 2 year period.
eligibility period is extended under 4(1A)
    AND is an incapacitated person
    AND compensable disability caused or contributed to failure to apply within 2 year period

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 10 - Application for certificate
# Original: (3) An application by a person who is not an eligible person but who is the surviving spouse or de facto partner of a deceased eligible person must be made within 2 years after...
surviving spouse application is within time limit
    OR deceased eligible person was an operational service member under 3A(1)
    OR surviving spouse application time limit satisfied

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 10 - Application for certificate
# Original: (3) ...must be made within 2 years after: (a) if the eligible person was not a member—his or her resignation, retirement or discharge...took effect; or (b) in any other case—the death of the eligible person.
surviving spouse application time limit satisfied
    OR surviving spouse time limit virtual one
        AND deceased was not a member
        AND application for entitlement certificate date - person's resignation retirement or discharge date <= surviving spouse application window years
    OR surviving spouse time limit virtual two
        AND deceased was a member
        AND application for entitlement certificate date - deceased person's date of death <= surviving spouse application window years

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 12 - Criteria for issue of certificate
# Original: (1) The Secretary must not issue an entitlement certificate to a person unless satisfied that...
entitlement certificate can be issued
    AND is not the holder of an entitlement certificate that is in force
    AND is an eligible person or surviving spouse of one
    AND has met service completion requirement if applicable
    AND subsidy period has not ended
    AND has not already been issued with an entitlement certificate on or after 1 July 2008
    AND application is made before finishing day
    AND previous certificate issue limit not exceeded
    OR special circumstances for re-issue apply

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 12 - Criteria for issue of certificate
# Original: (1)(b) the person: (i) is an eligible person, or was an eligible person when he or she applied for the certificate; or (ii) is the surviving spouse or de facto partner of such an eligible person;
is an eligible person or surviving spouse of one
    OR eligible person
    OR person is a surviving spouse or de facto partner

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 12 - Criteria for issue of certificate
# Original: (1)(c)...completed 6 months of effective full-time service after the end of the person’s basic service period; (d)...completed 6 months of effective full-time service; (e)...completed 6 months of effective full-time service after becoming a rejoining member
has met service completion requirement if applicable
    OR NOT is a member who requires additional service
    OR completed 6 months effective full-time service after basic service period
    OR is operational service member 3A(3) and completed 6 months effective full-time service
    OR is rejoining member not entitled to subsidy period and completed 6 months effective full-time service after rejoining

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 12 - Criteria for issue of certificate
# Original: (6) An entitlement certificate must not be issued after the finishing day.
application is made before finishing day
    OR application before finishing day virtual one
        AND is an eligible person who is a member of the Defence Force
        AND NOT is an operational service member
        AND application for entitlement certificate date <= finishing day for member certificate issue
    OR application for entitlement certificate date <= finishing day general

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 12 - Criteria for issue of certificate
# Original: (2) The Secretary must not issue an entitlement certificate to an eligible person who is not a member...if: (a) 2 or more entitlement certificates were previously issued to the person; and (b) at least one of those certificates was issued after the day on which the person’s resignation, retirement or discharge...took effect.
previous certificate issue limit not exceeded
    OR person is a member of the Defence Force
    OR number of entitlement certificates previously issued < 2
    OR NOT at least one previous certificate was issued after discharge

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 12 - Criteria for issue of certificate
# Original: (4) ...where a subsidised loan to a person who was an entitled person is discharged as a result of: (a) the destruction of the house... (b) the compulsory acquisition... (c) the sale or transfer of the property... under an order of a court... the Secretary must issue to the person an entitlement certificate if the person applies for the certificate within 12 months after the loan is discharged. (5) ...where...a subsidised loan is made to a person; and...the person is discharged from the Defence Force...because of any compensable disability...and...the subsidised loan is discharged as a result of the sale or transfer of the property...the Secretary must issue to the person an entitlement certificate if...the sale or transfer was reasonably necessary as a result of that disability.
special circumstances for re-issue apply
    OR re-issue due to discharge event
    OR re-issue due to disability related sale

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 12 - Criteria for issue of certificate
# Original: (4) ...where a subsidised loan to a person who was an entitled person is discharged as a result of: (a) the destruction of the house... (b) the compulsory acquisition... (c) the sale or transfer of the property... under an order of a court...
re-issue due to discharge event
    AND has previously received a subsidised loan
    AND previous loan discharged due to destruction of house OR previous loan discharged due to compulsory acquisition OR previous loan discharged due to court order sale
    AND application for entitlement certificate date - previous loan discharge date <= loan discharge application window months

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 12 - Criteria for issue of certificate
# Original: (5) ...where...a subsidised loan is made to a person; and...the person is discharged from the Defence Force...because of any compensable disability...and...the subsidised loan is discharged as a result of the sale or transfer of the property...the Secretary must issue to the person an entitlement certificate if...the sale or transfer was reasonably necessary as a result of that disability.
re-issue due to disability related sale
    AND has previously received a subsidised loan
    AND person was discharged from the Defence Force because of a compensable disability
    AND previous loan discharge date due to sale or transfer
    AND previous loan sale was reasonably necessary as a result of disability
    AND application for entitlement certificate date - previous loan discharge date <= loan discharge application window months

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 20 - When does subsidy become payable?
# Original: (2) Subsidy does not become payable on a loan to a person unless and until the Secretary is satisfied that...
subsidy is payable
    AND person is an entitled person
    AND subsidy period has not ended
    AND each borrower has consented to recovery of amounts
    AND person or spouse is not the owner of any other house in Australia
    AND house ownership and use criteria are met
    AND loan is secured by a first mortgage
    AND loan has been used for a valid purpose
    AND not excluded by section 20A
    AND not excluded by section 20(4)

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 20 - When does subsidy become payable?
# Original: (2)(e) the house in respect of which the loan was made: (i) is owned by the person... (ii) is used by the person as a home... (iii) is suitable for use as such a home... (iv) is not ordinarily used for the purpose of carrying on a business, trade or profession
house ownership and use criteria are met
    AND house is owned solely by person or jointly with spouse or de facto partner
    AND house is used as a home for the person and family
    AND house is suitable for use as a home
    AND house is not ordinarily used for carrying on a business trade or profession

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 20A - Condition of payment of subsidy—subsidy under one scheme only
# Original: (2) Subsidy is not payable on a loan to the person under this Act on or after the earliest day the 2008 Act subsidy became payable.
not excluded by section 20A
    AND NOT subsidy under Defence Home Ownership Assistance Scheme Act 2008 is or has been payable

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 21 - Maximum amounts on which subsidy is payable
# Original: (1) ...the amount on which subsidy is payable is: (a) the advanced amount; or (b) $80,000; whichever is less.
amount on which subsidy is payable IS CALC ( MIN ( total borrowed amount , maximum allowed amount ) )
    NEEDS total borrowed amount
    NEEDS maximum allowed amount

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 21 - Maximum amounts on which subsidy is payable
# Original: (1) ...the amount on which subsidy is payable is: (a) the advanced amount...
total borrowed amount IS CALC ( wishes to increase advanced amount ? ( advanced amount + proposed loan increase amount ) : advanced amount )
    NEEDS wishes to increase advanced amount
    NEEDS advanced amount
    NEEDS proposed loan increase amount

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 26 - Joint loans to entitled persons who are spouses or de facto partners
# Original: (1) Where a subsidised loan is made to 2 entitled persons jointly, each of whom is the spouse or de facto partner of the other...the references in...to $80,000 were references to $160,000
maximum allowed amount IS CALC ( is joint loan to entitled spouses ? maximum advanced amount for joint loan : maximum advanced amount )
    NEEDS is joint loan to entitled spouses
    NEEDS maximum advanced amount for joint loan
    NEEDS maximum advanced amount

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 23 - Subsidy period—eligible persons
# Original: (2) An eligible person is at any particular time entitled to a subsidy period, being a period that at that time equals the person’s entitlement period less the person’s used subsidy period (if any).
subsidy period months IS CALC ( ( entitlement period years * 12 ) - used subsidy period months )
    NEEDS entitlement period years
    NEEDS used subsidy period months

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 23 - Subsidy period—eligible persons
# Original: (3) In this section: entitlement period means...
entitlement period years IS CALC ( person's status for entitlement period = "member" ? member entitlement period : ( person's status for entitlement period = "warlike service member" ? warlike service member entitlement period : entitlement period maximum years standard ) )
    WANTS person's status for entitlement period
    NEEDS member entitlement period
    NEEDS warlike service member entitlement period
    NEEDS entitlement period maximum years standard

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 23 - Subsidy period—eligible persons
# Original: (3)(a) in relation to a member...(i) the number of completed years of subsidy service served by the member after completing his or her basic service period; or (ii) 20 years; whichever is less;
member entitlement period IS CALC ( MIN ( years of subsidy service after basic period , entitlement period maximum years standard ) )
    NEEDS years of subsidy service after basic period
    NEEDS entitlement period maximum years standard

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 23 - Subsidy period—eligible persons
# Original: (3)(bb) in relation to a person who is or has been a warlike service member: (i) the total of: (A) the number of completed years (if any) of subsidy service served by the person; and (B) the number of additional years of subsidy to which the person is entitled under subsection (5); or (ii) 25 years; whichever is less;
warlike service member entitlement period IS CALC ( MIN ( subsidy service years + additional years for warlike service , entitlement period maximum years warlike service member ) )
    NEEDS subsidy service years
    NEEDS additional years for warlike service
    NEEDS entitlement period maximum years warlike service member

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 23 - Subsidy period—eligible persons
# Original: (5) A person who is or has been a warlike service member is entitled to additional years of subsidy in accordance with the following table...
additional years for warlike service IS CALC ( warlike service period months > 9 ? 5 : ( warlike service period months > 6 ? 4 : ( warlike service period months > 3 ? 3 : 2 ) ) )
    NEEDS warlike service period months

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 23 - Subsidy period—eligible persons
# Original: (6) If a warlike service member is repatriated from warlike service because of wounds, injury or illness, he or she is taken for the purposes of subsection (5) to have continued to perform that warlike service until the end of...
warlike service period months IS CALC ( repatriated from warlike service due to wounds injury or illness ? expected posting period on warlike service months : actual warlike service months )
    NEEDS repatriated from warlike service due to wounds injury or illness
    NEEDS expected posting period on warlike service months
    NEEDS actual warlike service months

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 25 - Calculation of amounts of subsidy
# Original: (2) The RMR amount must be worked out using the formula: (LA × BR / 12) / (1 - (1 + BR / 12)^(-300))
RMR amount IS CALC ( ( amount on which subsidy is payable * benchmark rate / 12 ) / ( 1 - ( 1 + benchmark rate / 12 ) ^ ( - loan repayment term in months ) ) )
    NEEDS amount on which subsidy is payable
    NEEDS benchmark rate
    NEEDS loan repayment term in months

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 25 - Calculation of amounts of subsidy
# Original: (3) The monthly subsidy amount must be worked out using the formula: (RMR × 300 - LA) × 0.4 / 300
monthly subsidy amount IS CALC ( ( RMR amount * loan repayment term in months - amount on which subsidy is payable ) * subsidy interest component multiplier / loan repayment term in months )
    NEEDS RMR amount
    NEEDS loan repayment term in months
    NEEDS amount on which subsidy is payable
    NEEDS subsidy interest component multiplier

# Reference: https://www.legislation.gov.au/C2004A04103/latest/text
# Section: 29 - When does subsidy stop?
# Original: Subject to sections 27 and 28, subsidy stops being payable on a subsidised loan to a person who is a subsidised borrower when any of the following things happen...
subsidy stops being payable
    OR all outstanding amounts due under the loan are paid
    OR subsidy period ends
    OR joint tenancy is converted into a tenancy in common
    OR property is transferred under court order
    OR property is sold or transferred without approval
    OR person to whom 30(6) applies dies
    OR eligible person dies without surviving spouse or de facto partner
    OR eligible person dies and property transferred to someone other than surviving spouse or de facto partner