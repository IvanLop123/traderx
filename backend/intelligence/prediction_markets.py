"""Explicit probability assumptions, uncertainty and cost-adjusted research edges."""
from scipy.stats import beta
from backend.schemas.contracts import FairProbabilityEstimate, OpportunityEstimate, AssetIdentifier

def probability_from_outcomes(successes,total,evidence_ids,prior_success=1,prior_failure=1):
    if not 0<=successes<=total or prior_success<=0 or prior_failure<=0:raise ValueError('Invalid counts or prior')
    a=successes+prior_success;b=total-successes+prior_failure
    return FairProbabilityEstimate(probability=a/(a+b),lower=float(beta.ppf(.025,a,b)),upper=float(beta.ppf(.975,a,b)),
        evidence_ids=evidence_ids,assumptions=['Exchangeable historical outcomes','Beta-Binomial prior; structural changes may invalidate frequencies'],
        calibration={'method':'beta_binomial','observations':total,'validated':False})

def opportunity(market_id,yes_ask,fair:FairProbabilityEstimate,fee,liquidity,expiration):
    if not 0<=yes_ask<=1 or fee<0 or liquidity<0:raise ValueError('Invalid market probability, fee or liquidity')
    uncertainty=fair.probability-fair.lower
    return OpportunityEstimate(instrument=AssetIdentifier(symbol=market_id,asset_class='prediction',market_id=market_id),
        market_value=yes_ask,fair_value=fair.probability,raw_edge=fair.probability-yes_ask,uncertainty=uncertainty,
        estimated_costs=fee,estimated_net_edge=fair.lower-yes_ask-fee,liquidity=liquidity,expiration=expiration,evidence_ids=fair.evidence_ids)
